import os
import random
import streamlit as st
import feedparser
import google.generativeai as genai

# --- 1. SIDA OCH TILLGÄNGLIGHETSINSTÄLLNINGAR ---
st.set_page_config(
    page_title="Morgonposten – AI Briefing",
    page_icon="☕",
    layout="centered"
)

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
    for namn, url in kallor.items():
        try:
            feed = feedparser.parse(url)
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

                samlad_data += f"Rubrik: {entry.title}\nInfo: {getattr(entry, 'summary', '')}\nLänk: {lank}\nBild: {bild_url}\nKälla: {namn}\n\n"
        except Exception:
            continue

    return samlad_data

def generera_briefing(rådata):
    if not model:
        return "⚠️ API-nyckel saknas. Lägg till din GEMINI_API_KEY under 'Secrets' i Streamlit Cloud."

    prompt = f"""
    Du är en källkritisk nyhetsanalytiker och litteraturkännare för en person som läser sista året på gymnasiet (samhällsvetenskap).
    Läsaren har nystagmus och kronisk migrän. Skriv mycket tydligt, använd korta avsnitt och ha ett lugnt, pedagogiskt tilltal.

    Här är rådata från det senaste dygnet:
    {rådata}

    Skapa en morgonbriefing på SVENSKA med exakt följande rubrikstruktur:

    1. ### 🇸🇪 1. SVERIGE & VALET
    <small>Inrikespolitik, lagförslag och riksdagsbeslut</small>
    (250-400 ord)

    2. ### 🇳🇴 2. NORDEN
    <small>Samhälle och utveckling i grannländerna</small>
    (250-400 ord)

    3. ### 🏛️ 3. GLOBALT – GEOPOLITIK
    <small>Internationell politik och djupanalys</small>
    (350-500 ord)

    4. ### ⚖️ 4. GLOBALT – MÄNSKLIGA RÄTTIGHETER
    <small>Internationella relationer, FN och EU</small>
    (250-400 ord)

    5. ### 📈 5. GLOBALT – SAMHÄLLE & EKONOMI
    <small>Demografi och global utveckling</small>
    (250-400 ord)

    6. ### 🤖 6. TEKNIK & AI
    <small>Tekniska genombrott och ny lagstiftning</small>
    (150-250 ord)

    7. ### 🔬 7. VETENSKAP & HÄLSA
    <small>Medicinska och miljömässiga upptäckter</small>
    (150-250 ord)

    8. ### 📚 8. DAGENS KLASSIKER
    En bok utgiven för minst ett år sedan (eller tidigare). Inga parenteser i rubriken. Titel, författare, utgivningsår, genre, blurb (3-4 meningar) och bildlänk till omslaget.

    9. ### 📖 9. DAGENS NYA BOKREKOMMENDATION
    En nyligen utgiven bok. Inga parenteser i rubriken. Titel, författare, utgivningsår, genre, blurb (3-4 meningar) och bildlänk till omslaget.

    10. ### ☀️ 10. MORGONENS TANKE ELLER SKÄMT
    Ge antingen ett rart, fundersamt filosofiskt citat/tanke eller ett oskyldigt, trevligt skämt för att avsluta rapporten på ett varmt sätt.

    REGLER:
    - Inkludera källa, artikel-länk och bildlänk längst ned i varje nyhet.
    - Förklara endast mer avancerade juridiska/statsvetenskapliga begrepp (t.ex. "ratificera", "suveränitetsprincip").
    """

    response = model.generate_content(prompt)
    return response.text

# --- 2. HUVUDGRÄNSSNITT ---
st.markdown("""
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
    </div>
""", unsafe_allow_html=True)

if st.button("☕ Hämta morgonens nyheter"):
    with st.spinner("Hämtar dagens nyheter i lugn och ro..."):
        nyhetsdata = hamta_kallmaterial()
        st.session_state['briefing'] = generera_briefing(nyhetsdata)
        st.session_state['rådata'] = nyhetsdata

# Visa briefing om den finns i minnet
if 'briefing' in st.session_state:
    st.markdown("---")
    st.markdown(st.session_state['briefing'], unsafe_allow_html=True)

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

                Svara pedagogiskt, lugnt och tydligt på svenska. Om användaren ber om att få fördjupa en nyhet eller få en specifik nyhet/uppdatering, använd rådatan eller din kunskap för att ge ett fylligt och intressant svar.
                """
                svar = model.generate_content(prompt_fråga)
                st.info(svar.text)
else:
    st.write("Klicka på knappen ovan för att starta dagens läsning.")
