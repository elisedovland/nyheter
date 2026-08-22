import os
import random
import streamlit as st
import feedparser
# from google import genai

# --- 1. SIDA OCH TILLGÄNGLIGHETSINSTÄLLNINGAR ---
st.set_page_config(
    page_title="Morgonposten – AI Briefing",
    page_icon="☕",
    layout="centered"  # Smal läskolumn för nystagmus
)

# CSS för optimal ergonomi vid nystagmus och migrän
st.markdown("""
    <style>
    /* Varm, dämpad bakgrund utan blått ljus */
    .stApp {
        background-color: #181816 !important;
        color: #E6E2DD !important;
    }

    /* Tidningshuvud */
    .header-box {
        text-align: center;
        border-bottom: 1px solid #33322E;
        padding-bottom: 20px;
        margin-bottom: 30px;
    }
    .header-title {
        font-family: Georgia, serif !important;
        font-size: 30px !important;
        color: #F0EAE1 !important;
        margin: 0 !important;
        letter-spacing: 1px !important;
    }
    .header-subtitle {
        font-size: 16px !important;
        color: #A8A29E !important;
        margin-top: 8px !important;
    }

    /* Brödtext: Optimerad för nystagmus */
    p, li, label, div {
        font-family: "Atkinson Hyperlegible", Verdana, -apple-system, sans-serif !important;
        font-size: 20px !important;
        line-height: 1.85 !important;
        color: #E6E2DD !important;
        letter-spacing: 0.4px !important;
        word-spacing: 1px !important;
        text-align: left !important;
    }

    /* Rubriker */
    h1, h2, h3, h4 {
        color: #F0EAE1 !important;
        font-weight: 600 !important;
        margin-top: 1.4em !important;
        margin-bottom: 0.1em !important;
    }

    small {
        font-size: 15px !important;
        color: #A8A29E !important;
        display: block;
        margin-bottom: 14px !important;
    }

    /* Dämpade bilder */
    img {
        border-radius: 6px;
        filter: brightness(0.85) contrast(0.95);
    }

    /* Varma, dämpade knappar och fält */
    .stButton>button {
        background-color: #272623 !important;
        color: #E6E2DD !important;
        border: 1px solid #44423D !important;
        font-size: 18px !important;
        padding: 12px 26px !important;
        border-radius: 6px !important;
    }
    .stButton>button:hover {
        background-color: #33322E !important;
        border-color: #55534C !important;
    }

    input {
        background-color: #272623 !important;
        color: #E6E2DD !important;
        font-size: 18px !important;
        border: 1px solid #44423D !important;
    }
    </style>
""", unsafe_allow_html=True)

# Starta Gemini Client
client = None

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

    return samlad_data

def generera_briefing(rådata):
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

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    return response.text

# --- 2. HUVUDGRÄNSSNITT ---
st.markdown("""
    <div class="header-box">
        <div class="header-title">☕ MORGONPOSTEN</div>
        <div class="header-subtitle">🌱 Lugn AI-briefing & Litteratur i din egen takt 🌿</div>
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

    # Sök- & Frågesektion
    st.markdown("---")
    st.subheader("🔎 Ställ en fråga om nyheterna eller litteraturen")

    användar_fråga = st.text_input("Skriv din fråga här:")
    if användar_fråga:
        with st.spinner("Söker svar..."):
            prompt_fråga = f"""
            Briefing: {st.session_state['briefing']}
            Användarens fråga: {användar_fråga}
            Besvara pedagogiskt och sakligt på svenska.
            """
            svar = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt_fråga
            )
            st.info(svar.text)
else:
    st.write("Klicka på knappen ovan för att starta dagens läsning.")
