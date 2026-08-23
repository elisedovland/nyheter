import os
import re
from datetime import datetime
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import streamlit as st
import feedparser
import google.generativeai as genai

# --- 1. SIDA OCH TILLGÄNGLIGHETSINSTÄLLNINGAR ---
st.set_page_config(
    page_title="Morgonposten – AI Briefing",
    page_icon="☀️",
    layout="centered"
)

with st.sidebar.expander("Läsinställningar", expanded=False):
    textstorlek = st.select_slider(
        "Textstorlek",
        options=["Mindre", "Normal", "Större"],
        value="Normal",
    )
    radavstand = st.select_slider(
        "Radavstånd",
        options=["Kompakt", "Luftigt", "Extra luftigt"],
        value="Luftigt",
    )
    innehallsbredd = st.select_slider(
        "Textbredd",
        options=["Smal", "Normal", "Bred"],
        value="Normal",
    )
    hog_kontrast = st.toggle("Hög kontrast", value=False)
    minska_bilder = st.toggle("Dölj nyhetsbilder", value=False)

textstorlekar = {"Mindre": 18, "Normal": 20, "Större": 23}
radavstand_varden = {"Kompakt": 1.55, "Luftigt": 1.85, "Extra luftigt": 2.1}
bredd_varden = {"Smal": 680, "Normal": 820, "Bred": 1000}
bakgrund = "#FFFDF7" if hog_kontrast else "#F7F4EA"
textfarg = "#111111" if hog_kontrast else "#2C2A29"

# CSS för optimal ergonomi vid nystagmus och migrän
st.markdown("""
    <style>
    .stApp {
        background-color: #F7F4EA !important;
        color: #2C2A29 !important;
    }
    .header-box {
        text-align: center;
        border-top: 1px solid #8F8778;
        border-bottom: 3px double #8F8778;
        padding: 18px 0 22px;
        margin-bottom: 35px;
    }
    .masthead {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 18px;
    }
    .header-title {
        font-family: Georgia, serif !important;
        font-size: 32px !important;
        color: #1A1918 !important;
        margin: 0 !important;
        letter-spacing: 2.5px !important;
        font-weight: 700 !important;
        line-height: 1.2 !important;
        text-align: center !important;
    }
    .sun-symbol {
        width: 38px;
        height: 38px;
        flex: 0 0 38px;
        color: #756B5C;
    }
    .sun-symbol.right {
        transform: scaleX(-1);
    }
    @media (max-width: 480px) {
        .masthead {
            gap: 10px;
        }
        .header-title {
            font-size: 25px !important;
            letter-spacing: 1.5px !important;
        }
        .sun-symbol {
            width: 29px;
            height: 29px;
            flex-basis: 29px;
        }
    }
    .header-subtitle {
        font-size: 18px !important;
        color: #5C564F !important;
        margin-top: 8px !important;
        letter-spacing: 0.8px !important;
        text-align: center !important;
    }
    .edition-date {
        font-family: Georgia, serif !important;
        font-size: 14px !important;
        line-height: 1.4 !important;
        color: #756B5C !important;
        letter-spacing: 0.7px !important;
        margin-top: 5px !important;
        text-align: center !important;
    }
    p, li, label, div {
        font-family: "Atkinson Hyperlegible", Verdana, -apple-system, sans-serif !important;
        font-size: 20px !important;
        line-height: 1.85 !important;
        color: #2C2A29 !important;
        letter-spacing: 0.4px !important;
        word-spacing: 1px !important;
        text-align: left !important;
    }
    h1, h2, h3, h4 {
        color: #1A1918 !important;
        font-weight: 600 !important;
        margin-top: 1.4em !important;
        margin-bottom: 0.1em !important;
    }
    small {
        font-size: 15px !important;
        color: #5C564F !important;
        display: block;
        margin-bottom: 14px !important;
    }
    img {
        border-radius: 6px;
        filter: brightness(0.95) contrast(0.95);
    }
    .stButton>button {
        background-color: #E6E0D0 !important;
        color: #2C2A29 !important;
        border: 1px solid #C4BCA8 !important;
        font-size: 18px !important;
        padding: 12px 26px !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
    }
    .stButton>button:hover {
        background-color: #D9D2BF !important;
        border-color: #A89F8B !important;
    }
    input, textarea {
        background-color: #FFFFFF !important;
        color: #2C2A29 !important;
        font-size: 18px !important;
        border: 1px solid #C4BCA8 !important;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown(
    f"""
    <style>
    .stApp {{
        background-color: {bakgrund} !important;
        color: {textfarg} !important;
    }}
    .block-container {{
        max-width: {bredd_varden[innehallsbredd]}px !important;
    }}
    p, li, label, div {{
        font-size: {textstorlekar[textstorlek]}px !important;
        line-height: {radavstand_varden[radavstand]} !important;
        color: {textfarg} !important;
    }}
    {'.stApp img { display: none !important; }' if minska_bilder else ''}
    </style>
    """,
    unsafe_allow_html=True,
)

# Konfigurera Gemini med gemini-flash-latest som fungerar med nya nycklar
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-flash-latest')
else:
    model = None

def hamta_kallmaterial():
    kallor = {
        "SVT Nyheter": "https://www.svt.se/nyheter/rss.xml",
        "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "Deutsche Welle": "https://rss.dw.com/rdf/rss-en-all",
        "UN News": "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
        "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
        "AllAfrica Global": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
        "The Hindu (Indien)": "https://www.thehindu.com/news/international/feeder/default.rss"
    }

    samlad_data = ""
    kallstatus = []
    artikelnummer = 1
    for namn, url in kallor.items():
        try:
            request = Request(url, headers={"User-Agent": "Morgonposten/1.0"})
            with urlopen(request, timeout=12) as response:
                feed = feedparser.parse(response.read())

            if getattr(feed, "bozo", False) and not feed.entries:
                raise ValueError("RSS-flödet kunde inte tolkas")
            if not feed.entries:
                raise ValueError("RSS-flödet innehöll inga artiklar")

            samlad_data += f"\n--- KÄLLSEKTION: {namn} ---\n"
            for entry in feed.entries[:3]:
                lank = getattr(entry, 'link', 'Länk saknas')
                bild_url = "Ingen bild tillgänglig"
                if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                    bild_url = entry.media_thumbnail[0]['url']
                elif hasattr(entry, 'enclosures') and entry.enclosures:
                    for me in entry.enclosures:
                        if me.get('type', '').startswith('image/'):
                            bild_url = me.get('href', bild_url)
                            break

                samlad_data += (
                    f"ARTIKEL-ID: A{artikelnummer}\n"
                    f"Rubrik: {entry.title}\n"
                    f"Info: {getattr(entry, 'summary', '')}\n"
                    f"Länk: {lank}\n"
                    f"Bild: {bild_url}\n"
                    f"Källa: {namn}\n\n"
                )
                artikelnummer += 1
            kallstatus.append({"namn": namn, "ok": True, "meddelande": "Uppdaterad"})
        except Exception as error:
            kallstatus.append(
                {"namn": namn, "ok": False, "meddelande": str(error) or "Okänt fel"}
            )

    return samlad_data, kallstatus


def visa_kallstatus(kallstatus):
    fungerande = sum(status["ok"] for status in kallstatus)
    st.caption(f"Källor: {fungerande} av {len(kallstatus)} uppdaterades.")
    with st.expander("Visa källstatus", expanded=fungerande == 0):
        for status in kallstatus:
            markering = "✓" if status["ok"] else "–"
            st.write(f"{markering} **{status['namn']}** — {status['meddelande']}")


def dela_upp_briefing(briefing):
    rubriker = list(re.finditer(r"(?m)^###\s+(.+?)\s*$", briefing))
    if not rubriker:
        return []

    sektioner = []
    for index, rubrik in enumerate(rubriker):
        start = rubrik.end()
        slut = rubriker[index + 1].start() if index + 1 < len(rubriker) else len(briefing)
        innehall = briefing[start:slut].strip()
        kort_sagt = re.search(r"\*\*Kort sagt:\*\*\s*(.+?)(?:\n\n|$)", innehall, re.DOTALL)
        sammanfattning = kort_sagt.group(1).strip() if kort_sagt else "Öppna avsnittet för att läsa mer."
        if kort_sagt:
            innehall = (innehall[:kort_sagt.start()] + innehall[kort_sagt.end():]).strip()
        sektioner.append((rubrik.group(1), sammanfattning, innehall))
    return sektioner


def visa_briefing(briefing):
    sektioner = dela_upp_briefing(briefing)
    if not sektioner:
        st.markdown(briefing)
        return

    for rubrik, sammanfattning, innehall in sektioner:
        st.markdown(f"### {rubrik}")
        st.markdown(f"**Kort sagt:** {sammanfattning}")
        with st.expander("Läs hela avsnittet"):
            st.markdown(innehall)

def generera_briefing(rådata):
    if not model:
        return "⚠️ API-nyckel saknas. Lägg till din GEMINI_API_KEY under 'Secrets' i Streamlit Cloud."

    prompt = f"""
    Du är en källkritisk nyhetsanalytiker och litteraturkännare för en person som läser sista året på gymnasiet (samhällsvetenskap).
    Läsaren har nystagmus och kronisk migrän. Skriv mycket tydligt, använd korta avsnitt och ha ett lugnt, pedagogiskt tilltal.

    Här är ditt enda tillåtna nyhetsunderlag från det senaste dygnet:
    {rådata}

    KÄLLREGLER FÖR NYHETER:
    - Använd endast fakta som uttryckligen finns i nyhetsunderlaget ovan. Fyll inte luckor med egen kunskap.
    - Om underlaget inte räcker för en sektion, skriv tydligt att säkert underlag saknas. Hitta inte på en nyhet.
    - Varje nyhetsartikel måste avslutas med exakt artikel-ID, källnamn och den länk som hör till artikeln i underlaget.
    - Kopiera länken exakt. Skapa eller gissa aldrig en länk eller bildlänk.
    - Skilj tydligt mellan verifierade uppgifter och analys. Inled analys med "Analys:".
    - Bokrekommendationerna och morgonens tanke är redaktionellt material och omfattas inte av kravet på RSS-källa.

    Skapa en morgonbriefing på SVENSKA med exakt följande rubrikstruktur:

    ### 🇸🇪 1. SVERIGE & VALET
    *Inrikespolitik, lagförslag och riksdagsbeslut*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (250-400 ord)

    ### 🇳🇴 2. NORDEN
    *Samhälle och utveckling i grannländerna*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (250-400 ord)

    ### 🏛️ 3. GLOBALT – GEOPOLITIK
    *Internationell politik och djupanalys*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (350-500 ord)

    ### ⚖️ 4. GLOBALT – MÄNSKLIGA RÄTTIGHETER
    *Internationella relationer, FN och EU*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (250-400 ord)

    ### 📈 5. GLOBALT – SAMHÄLLE & EKONOMI
    *Demografi och global utveckling*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (250-400 ord)

    ### 🤖 6. TEKNIK & AI
    *Tekniska genombrott och ny lagstiftning*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (150-250 ord)

    ### 🔬 7. VETENSKAP & HÄLSA
    *Medicinska och miljömässiga upptäckter*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (150-250 ord)

    ### 📚 8. DAGENS KLASSIKER
    **Kort sagt:** Presentera boken i en kort mening.
    En bok utgiven för minst ett år sedan (eller tidigare). Inga parenteser i rubriken. Titel, författare, utgivningsår, genre, blurb (3-4 meningar) och bildlänk till omslaget.

    ### 📖 9. DAGENS NYA BOKREKOMMENDATION
    **Kort sagt:** Presentera boken i en kort mening.
    En nyligen utgiven bok. Inga parenteser i rubriken. Titel, författare, utgivningsår, genre, blurb (3-4 meningar) och bildlänk till omslaget.

    ### ☀️ 10. MORGONENS TANKE ELLER SKÄMT
    **Kort sagt:** Ge en kort inledning utan att avslöja hela poängen.
    Ge antingen ett rart, fundersamt filosofiskt citat/tanke eller ett oskyldigt, trevligt skämt för att avsluta rapporten på ett varmt sätt.

    REGLER:
    - Skriv källraden som: Källa: [KÄLLNAMN](EXAKT LÄNK) · Artikel-ID: A1
    - Inkludera bildlänk endast när underlaget innehåller en verklig bildlänk.
    - Förklara endast mer avancerade juridiska/statsvetenskapliga begrepp (t.ex. "ratificera", "suveränitetsprincip").
    """

    response = model.generate_content(prompt)
    return response.text

# --- 2. HUVUDGRÄNSSNITT ---
svenska_veckodagar = [
    "Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"
]
svenska_manader = [
    "januari", "februari", "mars", "april", "maj", "juni",
    "juli", "augusti", "september", "oktober", "november", "december",
]
nu = datetime.now(ZoneInfo("Europe/Stockholm"))
utgavedatum = f"{svenska_veckodagar[nu.weekday()]} {nu.day} {svenska_manader[nu.month - 1]} {nu.year} · Morgonutgåvan"

st.markdown(f"""
    <div class="header-box">
        <div class="masthead">
            <svg class="sun-symbol" aria-hidden="true" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="24" cy="24" r="7.5" stroke="currentColor" stroke-width="1.6"/>
                <circle cx="24" cy="24" r="3.5" fill="currentColor"/>
                <path d="M24 3v9M24 36v9M3 24h9M36 24h9M9.15 9.15l6.36 6.36M32.49 32.49l6.36 6.36M38.85 9.15l-6.36 6.36M15.51 32.49l-6.36 6.36" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                <path d="M17.2 5.1l2.4 7.4M28.4 35.5l2.4 7.4M5.1 30.8l7.4-2.4M35.5 19.6l7.4-2.4M5.1 17.2l7.4 2.4M35.5 28.4l7.4 2.4M17.2 42.9l2.4-7.4M28.4 12.5l2.4-7.4" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
            </svg>
            <div class="header-title">MORGONPOSTEN</div>
            <svg class="sun-symbol right" aria-hidden="true" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="24" cy="24" r="7.5" stroke="currentColor" stroke-width="1.6"/>
                <circle cx="24" cy="24" r="3.5" fill="currentColor"/>
                <path d="M24 3v9M24 36v9M3 24h9M36 24h9M9.15 9.15l6.36 6.36M32.49 32.49l6.36 6.36M38.85 9.15l-6.36 6.36M15.51 32.49l-6.36 6.36" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                <path d="M17.2 5.1l2.4 7.4M28.4 35.5l2.4 7.4M5.1 30.8l7.4-2.4M35.5 19.6l7.4-2.4M5.1 17.2l7.4 2.4M35.5 28.4l7.4 2.4M17.2 42.9l2.4-7.4M28.4 12.5l2.4-7.4" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
            </svg>
        </div>
        <div class="header-subtitle">Lugn AI-briefing &amp; litteratur i din egen takt</div>
        <div class="edition-date">{utgavedatum}</div>
    </div>
""", unsafe_allow_html=True)

if st.button("☕ Hämta morgonens nyheter"):
    with st.spinner("Hämtar dagens nyheter i lugn och ro..."):
        nyhetsdata, kallstatus = hamta_kallmaterial()
        st.session_state['kallstatus'] = kallstatus
        st.session_state['rådata'] = nyhetsdata
        if nyhetsdata:
            st.session_state['briefing'] = generera_briefing(nyhetsdata)
        else:
            st.session_state.pop('briefing', None)
            st.error("Inga nyhetskällor kunde hämtas. Försök igen om en stund.")

if 'kallstatus' in st.session_state:
    visa_kallstatus(st.session_state['kallstatus'])

# Visa briefing om den finns i minnet
if 'briefing' in st.session_state:
    st.markdown("---")
    visa_briefing(st.session_state['briefing'])

    # Interaktiv AI-chatt för begrepp, utökning och specifika nyheter
    st.markdown("---")
    st.subheader("💬 AI-assistent för dina frågor")
    st.write("Här kan du ställa frågor om ett svårt ord, be om att få en specifik nyhet expanderad, eller fråga efter andra nyheter och uppdateringar!")

    with st.form("fraga_till_assistenten", clear_on_submit=True):
        användar_fråga = st.text_area(
            "Vad funderar du på? (t.ex. 'Förklara ordet ratificera', 'Expandera nyhet 3' eller 'Berätta mer om valet i USA'):",
            height=140,
            placeholder="Skriv din fråga här. Du kan skriva på flera rader.",
        )
        skicka_fråga = st.form_submit_button("Fråga AI-assistenten")

    if skicka_fråga and användar_fråga.strip():
        if not model:
            st.error("⚠️ API-nyckel saknas för att använda chatten.")
        else:
            with st.spinner("AI-assistenten funderar..."):
                prompt_fråga = f"""
                Du är en tålmodig och pedagogisk AI-assistent för en gymnasieelev (samhällsklass) med nystagmus och migrän.
                
                Här är dagens rådata som nyheterna byggdes på:
                {st.session_state.get('rådata', 'Ingen rådata tillgänglig')}

                Här är den tidigare genererade briefingen:
                {st.session_state['briefing']}

                Användarens fråga / önskemål: {användar_fråga}

                Svara pedagogiskt, lugnt och tydligt på svenska. För aktuella nyheter får du endast använda rådatan ovan.
                Ange källnamn och kopiera artikelns länk exakt när du beskriver en nyhetsuppgift. Om frågan inte kan
                besvaras från rådatan ska du säga att uppgiften inte kan verifieras i dagens källunderlag. Använd inte
                egen kunskap för aktuella nyhetspåståenden och hitta aldrig på en källa eller länk.
                """
                svar = model.generate_content(prompt_fråga)
                st.info(svar.text)
else:
    st.write("Klicka på knappen ovan för att starta dagens läsning.")
