import html
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import streamlit as st
import feedparser
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

logger = logging.getLogger(__name__)
UTGAVECACHE = Path(__file__).with_name(".morgonposten-cache.json")


class GeminiKvotSlut(RuntimeError):
    """Geminis anropskvot är tillfälligt slut."""


KVOTMEDDELANDE = (
    "Dagens kostnadsfria AI-kvot är slut. En redan skapad utgåva visas fortfarande, "
    "men en ny kan inte skapas förrän Google har återställt kvoten. Försök igen senare."
)

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
        box-sizing: border-box;
        padding: 5px;
        border: 1px solid #C7B878;
        border-radius: 50%;
        background-color: #E9D99F;
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
    .bookplate {
        max-width: 360px;
        margin: 22px auto 28px !important;
        padding: 22px 24px 18px;
        border: 3px double #8F8778;
        background: #F2ECDD;
        box-shadow: inset 0 0 0 5px #F2ECDD, inset 0 0 0 6px #C4BCA8;
        text-align: center !important;
    }
    .bookplate-kicker,
    .bookplate-title,
    .bookplate-author,
    .bookplate-year,
    .bookplate-genre,
    .bookplate-signature {
        font-family: Georgia, serif !important;
        text-align: center !important;
        line-height: 1.35 !important;
    }
    .bookplate-kicker {
        font-size: 12px !important;
        letter-spacing: 2px !important;
        color: #756B5C !important;
    }
    .bookplate-symbol {
        width: 54px;
        height: 54px;
        margin: 12px auto 10px;
        color: #756B5C;
    }
    .bookplate-title {
        font-size: 23px !important;
        letter-spacing: 1.2px !important;
        font-weight: 700 !important;
        color: #1A1918 !important;
        text-transform: uppercase;
    }
    .bookplate-author {
        font-size: 17px !important;
        margin-top: 6px !important;
        color: #2C2A29 !important;
    }
    .bookplate-year {
        font-size: 14px !important;
        color: #756B5C !important;
    }
    .bookplate-genre {
        border-top: 1px solid #C4BCA8;
        border-bottom: 1px solid #C4BCA8;
        font-size: 12px !important;
        letter-spacing: 1.4px !important;
        margin: 14px 18px 12px !important;
        padding: 5px 0 !important;
        color: #5C564F !important;
        text-transform: uppercase;
    }
    .bookplate-signature {
        font-size: 11px !important;
        letter-spacing: 2.5px !important;
        color: #756B5C !important;
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
    .st-key-starta_utgava,
    .st-key-starta_utgava .stButton {
        display: flex !important;
        width: 100% !important;
        justify-content: center !important;
        text-align: center !important;
    }
    .st-key-starta_utgava .stButton>button {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 150px !important;
        height: 150px !important;
        min-height: 150px !important;
        margin: 22px auto 14px !important;
        padding: 18px !important;
        border: 3px double #756B5C !important;
        border-radius: 50% !important;
        background: radial-gradient(
            circle at center,
            #FAF4D9 0%,
            #F0E4B8 52%,
            #DDCB8D 100%
        ) !important;
        box-shadow: inset 0 0 18px rgba(117, 107, 92, 0.08) !important;
        font-family: Georgia, serif !important;
        font-size: 19px !important;
        line-height: 1.25 !important;
        letter-spacing: 0.5px !important;
        text-align: center !important;
        white-space: normal !important;
    }
    .st-key-starta_utgava .stButton>button:hover {
        background: radial-gradient(
            circle at center,
            #FCF7E1 0%,
            #F3E8C1 52%,
            #E2D197 100%
        ) !important;
    }
    .st-key-starta_utgava .stButton>button p {
        width: 100% !important;
        margin: 0 !important;
        padding: 0 !important;
        font-family: Georgia, serif !important;
        font-size: 19px !important;
        line-height: 1.25 !important;
        text-align: center !important;
    }
    .button-vine {
        width: 210px;
        height: 62px;
        margin: -46px auto 12px;
        color: #6F985F;
    }
    .button-vine svg {
        display: block;
        width: 100%;
        height: 100%;
    }
    @media (max-width: 480px) {
        .button-vine {
            width: 180px;
            height: 54px;
            margin-top: -39px;
        }
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


@st.cache_resource
def hamta_utgavelager():
    """Läs färdiga utgåvor från disk och dela dem mellan appens besökare."""
    sparat = {"nyheter": {}, "redaktionellt": {}}
    try:
        if UTGAVECACHE.exists():
            inlast = json.loads(UTGAVECACHE.read_text(encoding="utf-8"))
            if isinstance(inlast, dict):
                sparat["nyheter"] = inlast.get("nyheter", {})
                sparat["redaktionellt"] = inlast.get("redaktionellt", {})
    except (OSError, json.JSONDecodeError, TypeError):
        logger.exception("Kunde inte läsa den sparade utgåvan")
    return {
        "nyheter": sparat["nyheter"],
        "redaktionellt": sparat["redaktionellt"],
        "pagar": set(),
        "lock": threading.Lock(),
    }


def spara_utgavelager(utgavelager):
    """Spara färdigt innehåll atomiskt så att det överlever en omstart."""
    tillfallig_fil = UTGAVECACHE.with_suffix(".tmp")
    data = {
        "nyheter": utgavelager["nyheter"],
        "redaktionellt": utgavelager["redaktionellt"],
    }
    tillfallig_fil.write_text(
        json.dumps(data, ensure_ascii=False),
        encoding="utf-8",
    )
    tillfallig_fil.replace(UTGAVECACHE)


def generera_text(prompt, timeout=90):
    """Anropa Gemini med en tydlig tidsgräns så att gränssnittet inte fastnar."""
    if not model:
        raise RuntimeError("Gemini API-nyckel saknas")
    try:
        response = model.generate_content(
            prompt,
            request_options={"timeout": timeout},
        )
    except ResourceExhausted as error:
        raise GeminiKvotSlut(KVOTMEDDELANDE) from error
    return response.text


KALLOR = {
    "SVT Nyheter": "https://www.svt.se/nyheter/rss.xml",
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Deutsche Welle": "https://rss.dw.com/rdf/rss-en-all",
    "UN News": "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "AllAfrica Global": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
    "The Hindu (Indien)": "https://www.thehindu.com/news/international/feeder/default.rss",
}


def rensa_rss_text(text, max_langd=900):
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_langd:
        return text
    return f"{text[:max_langd].rsplit(' ', 1)[0]}…"


def hamta_en_kalla(kalla):
    namn, url = kalla
    try:
        request = Request(url, headers={"User-Agent": "Morgonposten/1.0"})
        with urlopen(request, timeout=12) as response:
            feed = feedparser.parse(response.read())

        if getattr(feed, "bozo", False) and not feed.entries:
            raise ValueError("RSS-flödet kunde inte tolkas")
        if not feed.entries:
            raise ValueError("RSS-flödet innehöll inga artiklar")

        artiklar = []
        for entry in feed.entries[:3]:
            lank = str(getattr(entry, "link", "")).strip()
            rubrik = rensa_rss_text(getattr(entry, "title", "Rubrik saknas"), 220)
            sammanfattning = rensa_rss_text(getattr(entry, "summary", ""))
            artiklar.append(
                {
                    "rubrik": rubrik,
                    "sammanfattning": sammanfattning,
                    "lank": lank,
                    "kalla": namn,
                }
            )
        return namn, artiklar, None
    except Exception as error:
        return namn, [], str(error) or "Okänt fel"


@st.cache_data(ttl=86400, show_spinner=False)
def hamta_kallmaterial(nyhetsnyckel):
    """Hämta RSS-underlag en gång per schemalagd nyhetsutgåva."""
    _ = nyhetsnyckel
    with ThreadPoolExecutor(max_workers=4) as executor:
        resultat = list(executor.map(hamta_en_kalla, KALLOR.items()))

    artiklar = []
    kallstatus = []
    sedda_artiklar = set()
    for namn, kallartiklar, fel in resultat:
        if fel:
            kallstatus.append({"namn": namn, "ok": False, "meddelande": fel})
            continue

        tillagda = 0
        for artikel in kallartiklar:
            identitet = artikel["lank"] or artikel["rubrik"].casefold()
            if identitet in sedda_artiklar:
                continue
            sedda_artiklar.add(identitet)
            artikel["id"] = f"A{len(artiklar) + 1}"
            artiklar.append(artikel)
            tillagda += 1
        kallstatus.append(
            {"namn": namn, "ok": True, "meddelande": f"{tillagda} artiklar"}
        )

    block = []
    for artikel in artiklar:
        block.append(
            "\n".join(
                [
                    f"ARTIKEL-ID: {artikel['id']}",
                    f"Rubrik: {artikel['rubrik']}",
                    f"Info: {artikel['sammanfattning']}",
                    f"Länk: {artikel['lank']}",
                    f"Källa: {artikel['kalla']}",
                ]
            )
        )
    return "\n\n".join(block), kallstatus, artiklar


def visa_kallstatus(kallstatus):
    fungerande = sum(status["ok"] for status in kallstatus)
    st.caption(f"Källor: {fungerande} av {len(kallstatus)} uppdaterades.")
    st.caption("RSS-underlaget är låst till den aktuella 12-timmarsutgåvan.")
    with st.expander("Visa källstatus", expanded=fungerande == 0):
        for status in kallstatus:
            markering = "✓" if status["ok"] else "–"
            st.write(f"{markering} **{status['namn']}** — {status['meddelande']}")


SEKTIONER = [
    (1, "🇸🇪 1. SVERIGE & VALET"),
    (2, "🇳🇴 2. NORDEN"),
    (3, "🏛️ 3. GLOBALT – GEOPOLITIK"),
    (4, "⚖️ 4. GLOBALT – MÄNSKLIGA RÄTTIGHETER"),
    (5, "📈 5. GLOBALT – SAMHÄLLE & EKONOMI"),
    (6, "🤖 6. TEKNIK & AI"),
    (7, "🔬 7. VETENSKAP & HÄLSA"),
    (8, "📚 8. DAGENS KLASSIKER"),
    (9, "📖 9. DAGENS NYA BOKREKOMMENDATION"),
    (10, "☀️ 10. MORGONENS TANKE ELLER SKÄMT"),
]


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


def valj_kallunderlag(text, artiklar):
    artikel_idn = set(re.findall(r"\bA\d+\b", text))
    relevanta = [artikel for artikel in artiklar if artikel["id"] in artikel_idn]
    return "\n\n".join(
        (
            f"ARTIKEL-ID: {artikel['id']}\n"
            f"Rubrik: {artikel['rubrik']}\n"
            f"Info: {artikel['sammanfattning']}\n"
            f"Länk: {artikel['lank']}\n"
            f"Källa: {artikel['kalla']}"
        )
        for artikel in relevanta
    )


@st.cache_data(ttl=3600, show_spinner=False)
def generera_fordjupning(rubrik, avsnitt, kallunderlag):
    if not model:
        return "API-nyckel saknas för att skapa en fördjupning."

    prompt = f"""
    Skriv en lugn och pedagogisk svensk fördjupning på 300-450 ord om avsnittet "{rubrik}".
    Utgå från den korta texten och, för nyheter, endast från källunderlaget nedan.
    Lägg inte till aktuella fakta från egen kunskap. Skilj fakta från analys, och kopiera varje
    använd källas namn och länk exakt. Om underlaget inte räcker ska du säga det tydligt.

    KORT TEXT:
    {avsnitt}

    KÄLLUNDERLAG:
    {kallunderlag or 'Redaktionellt avsnitt utan RSS-underlag.'}
    """
    return generera_text(prompt, timeout=75)


@st.cache_data(ttl=3600, show_spinner=False)
def svara_pa_fraga(fraga, avsnitt, kallunderlag):
    if not model:
        return "API-nyckel saknas för att använda assistenten."

    prompt = f"""
    Du är en tålmodig och pedagogisk AI-assistent för en gymnasieelev med nystagmus och migrän.
    Svara lugnt, tydligt och kortfattat på svenska. För aktuella nyheter får du endast använda
    det valda avsnittet och källunderlaget nedan. Ange källnamn och kopiera länken exakt när du
    beskriver en nyhetsuppgift. Om frågan inte kan besvaras från materialet ska du säga det.
    Använd inte egen kunskap för aktuella nyhetspåståenden och hitta aldrig på en källa eller länk.

    VALT AVSNITT:
    {avsnitt}

    RELEVANT KÄLLUNDERLAG:
    {kallunderlag or 'Inget RSS-underlag är kopplat till det valda avsnittet.'}

    FRÅGA:
    {fraga}
    """
    return generera_text(prompt, timeout=60)


def genre_symbol(genre):
    genre_liten = genre.casefold()
    symboler = [
        (("myster", "deckar", "krim", "thriller"), '<circle cx="21" cy="21" r="10"/><path d="m29 29 12 12"/>'),
        (("histor",), '<path d="M14 8h20M14 40h20M17 12h14l-3 8-4 4-4-4-3-8Zm0 24h14l-3-8-4-4-4 4-3 8Z"/>'),
        (("science fiction", "sci-fi", "dystop"), '<circle cx="24" cy="24" r="4"/><ellipse cx="24" cy="24" rx="19" ry="8"/><ellipse cx="24" cy="24" rx="8" ry="19" transform="rotate(35 24 24)"/>'),
        (("fantasy", "fantasi"), '<path d="M30 7a17 17 0 1 0 11 27A15 15 0 1 1 30 7Z"/><path d="m36 10 1.5 3.5L41 15l-3.5 1.5L36 20l-1.5-3.5L31 15l3.5-1.5L36 10Z"/>'),
        (("romantik", "romance", "kärlek"), '<path d="M24 40V20M24 24c-9-2-11-9-8-14 7 1 10 6 8 14Zm0 4c9-2 11-9 8-14-7 1-10 6-8 14ZM19 34l-6 5M29 34l6 5"/>'),
        (("äventyr", "adventure", "reseskild"), '<circle cx="24" cy="24" r="18"/><circle cx="24" cy="24" r="3"/><path d="m29 19 6-6-4 10-7 1 5-5ZM19 29l-6 6 4-10 7-1-5 5Z"/>'),
        (("gotik", "gothic", "skräck", "horror"), '<path d="M19 40h10M21 40V24h6v16M24 24c-5-5 0-8 1-14 6 6 5 11-1 14ZM17 18h14M18 21h12"/>'),
        (("filosofi", "essä", "essay"), '<path d="M14 34h20M17 34v6h14v-6M19 31h10l3-8H16l3 8ZM24 23V10M20 14h8M18 10h12"/>'),
    ]
    innehall = '<path d="M8 13c7-2 12 0 16 4v24c-4-4-9-6-16-4V13Zm32 0c-7-2-12 0-16 4v24c4-4 9-6 16-4V13Z"/>'
    for nyckelord, kandidat in symboler:
        if any(ordet in genre_liten for ordet in nyckelord):
            innehall = kandidat
            break
    return (
        '<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{innehall}</svg>'
    )


def skapa_bokplatta(innehall, sektion_nummer):
    ren_text = re.sub(r"[*_`]", "", innehall)
    falt = {}
    for namn in ("Titel", "Författare", "Utgivningsår", "Genre"):
        traff = re.search(rf"(?im)^\s*{namn}:\s*(.+?)\s*$", ren_text)
        if traff:
            falt[namn] = traff.group(1).strip()
    if not all(namn in falt for namn in ("Titel", "Författare", "Genre")):
        return ""

    kicker = "DAGENS KLASSIKER" if sektion_nummer == 8 else "DAGENS NYA BOK"
    return f"""
    <div class="bookplate">
        <div class="bookplate-kicker">{kicker}</div>
        <div class="bookplate-symbol" aria-hidden="true">{genre_symbol(falt['Genre'])}</div>
        <div class="bookplate-title">{html.escape(falt['Titel'])}</div>
        <div class="bookplate-author">{html.escape(falt['Författare'])}</div>
        <div class="bookplate-year">{html.escape(falt.get('Utgivningsår', ''))}</div>
        <div class="bookplate-genre">{html.escape(falt['Genre'])}</div>
        <div class="bookplate-signature">MORGONPOSTEN</div>
    </div>
    """


def visa_briefing(briefing, artiklar):
    sektioner = dela_upp_briefing(briefing)
    if not sektioner:
        st.markdown(briefing)
        return

    sektioner_per_nummer = {}
    for rubrik, sammanfattning, innehall in sektioner:
        nummer = re.search(r"\b(10|[1-9])\.", rubrik)
        if nummer:
            sektioner_per_nummer[int(nummer.group(1))] = (rubrik, sammanfattning, innehall)

    st.session_state.setdefault("fordjupningar", {})
    for nummer, standardrubrik in SEKTIONER:
        sektion = sektioner_per_nummer.get(nummer)
        if not sektion:
            st.markdown(f"### {standardrubrik}")
            if nummer <= 7:
                st.info("Inget tillräckligt säkert underlag hittades för detta avsnitt idag.")
            else:
                st.info("Det redaktionella avsnittet kunde inte skapas den här gången.")
            continue

        rubrik, sammanfattning, innehall = sektion
        st.markdown(f"### {rubrik}")
        st.markdown(f"**Kort sagt:** {sammanfattning}")
        with st.expander("Läs det korta avsnittet"):
            st.markdown(innehall)
        if nummer in (8, 9):
            bokplatta = skapa_bokplatta(innehall, nummer)
            if bokplatta:
                st.markdown(bokplatta, unsafe_allow_html=True)
        if nummer < 10:
            if st.button("Skapa fördjupning", key=f"fordjupa_{nummer}"):
                kallunderlag = valj_kallunderlag(innehall, artiklar) if nummer <= 7 else ""
                with st.spinner("Skapar en fördjupning..."):
                    starttid = time.perf_counter()
                    try:
                        st.session_state["fordjupningar"][nummer] = generera_fordjupning(
                            rubrik,
                            f"{sammanfattning}\n\n{innehall}",
                            kallunderlag,
                        )
                        st.session_state["prestanda"]["fordjupning_sekunder"] = (
                            time.perf_counter() - starttid
                        )
                    except GeminiKvotSlut:
                        st.error(KVOTMEDDELANDE)
                    except Exception:
                        st.error("Fördjupningen kunde inte skapas just nu. Försök igen senare.")
            if nummer in st.session_state["fordjupningar"]:
                with st.expander("Fördjupning", expanded=True):
                    st.markdown(st.session_state["fordjupningar"][nummer])


@st.cache_data(ttl=172800, show_spinner=False)
def generera_nyhetsbriefing(rådata, nyhetsnyckel):
    """Skapa nyhetsdelarna en gång per 12-timmarsutgåva."""
    if not model:
        return "⚠️ API-nyckel saknas. Lägg till din GEMINI_API_KEY under 'Secrets' i Streamlit Cloud."

    prompt = f"""
    Du är en källkritisk nyhetsanalytiker för en person som läser sista året på gymnasiet (samhällsvetenskap).
    Läsaren har nystagmus och kronisk migrän. Skriv mycket tydligt, använd korta avsnitt och ha ett lugnt, pedagogiskt tilltal.
    Den schemalagda nyhetsutgåvan är {nyhetsnyckel} i tidszonen Europe/Stockholm.

    Här är ditt enda tillåtna nyhetsunderlag:
    {rådata}

    KÄLLREGLER FÖR NYHETER:
    - Använd endast fakta som uttryckligen finns i nyhetsunderlaget ovan. Fyll inte luckor med egen kunskap.
    - Om underlaget inte räcker för en sektion, skriv tydligt att säkert underlag saknas. Hitta inte på en nyhet.
    - Varje nyhetsartikel måste avslutas med exakt artikel-ID, källnamn och den länk som hör till artikeln i underlaget.
    - Kopiera nyhetslänken exakt. Skapa eller gissa aldrig en länk.
    - Inkludera inga bilder, bildadresser, omslagsbilder eller länkar till bilder.
    - Skilj tydligt mellan verifierade uppgifter och analys. Inled analys med "Analys:".
    - Utelämna helt en nyhetssektion (1-7) om det inte finns en relevant artikel i underlaget.
      Appen visar då automatiskt att säkert underlag saknas. Skriv inte utfyllnad om frånvaron.

    Skapa nyhetsdelen på SVENSKA. Hela svaret ska vara ungefär 550-800 ord.
    Använd följande rubriker för de sektioner som har underlag:

    ### 🇸🇪 1. SVERIGE & VALET
    *Inrikespolitik, lagförslag och riksdagsbeslut*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (80-120 ord)

    ### 🇳🇴 2. NORDEN
    *Samhälle och utveckling i grannländerna*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (80-120 ord)

    ### 🏛️ 3. GLOBALT – GEOPOLITIK
    *Internationell politik och djupanalys*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (100-140 ord)

    ### ⚖️ 4. GLOBALT – MÄNSKLIGA RÄTTIGHETER
    *Internationella relationer, FN och EU*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (80-120 ord)

    ### 📈 5. GLOBALT – SAMHÄLLE & EKONOMI
    *Demografi och global utveckling*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (80-120 ord)

    ### 🤖 6. TEKNIK & AI
    *Tekniska genombrott och ny lagstiftning*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (70-100 ord)

    ### 🔬 7. VETENSKAP & HÄLSA
    *Medicinska och miljömässiga upptäckter*
    **Kort sagt:** Sammanfatta avsnittet i 1-2 korta meningar.
    (70-100 ord)

    REGLER:
    - Skriv källraden som: Källa: [KÄLLNAMN](EXAKT LÄNK) · Artikel-ID: A1
    - Förklara endast mer avancerade juridiska/statsvetenskapliga begrepp (t.ex. "ratificera", "suveränitetsprincip").
    """

    return generera_text(prompt, timeout=90)


@st.cache_data(ttl=172800, show_spinner=False)
def generera_redaktionellt(dagsnyckel):
    """Skapa boktips och morgontanke en gång per Stockholmsdatum."""
    if not model:
        return ""

    prompt = f"""
    Du är litteraturkännare och redaktör för en lugn svensk morgontidning. Skapa dagens
    redaktionella innehåll för {dagsnyckel} i tidszonen Europe/Stockholm. Samma innehåll ska
    användas hela dagen. Skriv tydligt, varmt och kortfattat. Inkludera inga bilder,
    bildadresser, omslagsbilder eller länkar till bilder.

    ### 📚 8. DAGENS KLASSIKER
    **Kort sagt:** Presentera boken i en kort mening.
    En bok utgiven för minst ett år sedan (eller tidigare). Inga parenteser i rubriken.
    Skriv metadata på fyra egna rader i exakt detta format:
    Titel: bokens titel
    Författare: författarens namn
    Utgivningsår: årtal
    Genre: tydlig genre
    Skriv därefter en blurb på 2-3 meningar.

    ### 📖 9. DAGENS NYA BOKREKOMMENDATION
    **Kort sagt:** Presentera boken i en kort mening.
    En nyligen utgiven bok. Inga parenteser i rubriken.
    Skriv metadata på fyra egna rader i exakt detta format:
    Titel: bokens titel
    Författare: författarens namn
    Utgivningsår: årtal
    Genre: tydlig genre
    Skriv därefter en blurb på 2-3 meningar.

    ### ☀️ 10. MORGONENS TANKE ELLER SKÄMT
    **Kort sagt:** Ge en kort inledning utan att avslöja hela poängen.
    Ge antingen ett rart, fundersamt filosofiskt citat/tanke eller ett oskyldigt, trevligt skämt för att avsluta rapporten på ett varmt sätt.
    """

    return generera_text(prompt, timeout=75)

# --- 2. HUVUDGRÄNSSNITT ---
svenska_veckodagar = [
    "Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag"
]
svenska_manader = [
    "januari", "februari", "mars", "april", "maj", "juni",
    "juli", "augusti", "september", "oktober", "november", "december",
]
stockholm = ZoneInfo("Europe/Stockholm")
nu = datetime.now(stockholm)
if nu.hour < 12:
    nyhetsstart = nu.replace(hour=0, minute=0, second=0, microsecond=0)
else:
    nyhetsstart = nu.replace(hour=12, minute=0, second=0, microsecond=0)
nyhetsnyckel = nyhetsstart.strftime("%Y-%m-%d-%H")
redaktionell_nyckel = nu.date().isoformat()
utgavetyp = "Morgonutgåvan" if nu.hour < 12 else "Eftermiddagsutgåvan"
utgavedatum = f"{svenska_veckodagar[nu.weekday()]} {nu.day} {svenska_manader[nu.month - 1]} {nu.year} · {utgavetyp}"

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
        <div class="header-subtitle">AI-briefing med nyheter, böcker och morgontanke</div>
        <div class="edition-date">{utgavedatum}</div>
    </div>
""", unsafe_allow_html=True)

st.session_state.setdefault("prestanda", {})
if st.session_state.get("aktiv_nyhetsnyckel") != nyhetsnyckel:
    for nyckel in ("rådata", "artiklar", "kallstatus", "briefing"):
        st.session_state.pop(nyckel, None)
    st.session_state["fordjupningar"] = {}
elif st.session_state.get("aktiv_redaktionell_nyckel") != redaktionell_nyckel:
    st.session_state.pop("briefing", None)
    st.session_state["fordjupningar"] = {}
st.session_state["aktiv_nyhetsnyckel"] = nyhetsnyckel
st.session_state["aktiv_redaktionell_nyckel"] = redaktionell_nyckel

utgavelager = hamta_utgavelager()
startnyckel = f"{nyhetsnyckel}|{redaktionell_nyckel}"
nyhetsutgava = utgavelager["nyheter"].get(nyhetsnyckel)
redaktionell_utgava = utgavelager["redaktionellt"].get(redaktionell_nyckel)

if nyhetsutgava and redaktionell_utgava:
    briefing = f"{nyhetsutgava['text']}\n\n{redaktionell_utgava['text']}".strip()
    st.session_state["rådata"] = nyhetsutgava["rådata"]
    st.session_state["artiklar"] = nyhetsutgava["artiklar"]
    st.session_state["kallstatus"] = nyhetsutgava["kallstatus"]
    st.session_state["briefing"] = briefing
    st.session_state["prestanda"] = {
        **nyhetsutgava["prestanda"],
        **redaktionell_utgava["prestanda"],
        "utdataord": len(briefing.split()),
    }
    st.session_state.pop("startfel", None)
else:
    st.session_state.pop("briefing", None)
    starta_utgava = st.button(
        "Starta utgåvan",
        type="primary",
        key="starta_utgava",
        disabled=startnyckel in utgavelager["pagar"],
    )
    st.markdown(
        """
        <div class="button-vine" aria-hidden="true">
            <svg viewBox="0 -4 210 66" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M105 59C97 45 80 33 60 25C46 19 34 11 27 2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                <path d="M105 59C113 45 130 33 150 25C164 19 176 11 183 2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
                <path d="M72 31C65 22 57 20 52 23C56 29 63 33 72 31ZM54 22C50 14 43 11 38 13C42 19 48 23 54 22ZM38 13C35 7 29 5 25 7C28 12 33 14 38 13ZM30 9C28 0 23-4 17-3C18 4 23 8 30 9ZM138 31C145 22 153 20 158 23C154 29 147 33 138 31ZM156 22C160 14 167 11 172 13C168 19 162 23 156 22ZM172 13C175 7 181 5 185 7C182 12 177 14 172 13ZM180 9C182 0 187-4 193-3C192 4 187 8 180 9Z" fill="currentColor" fill-opacity="0.55" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/>
            </svg>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if starta_utgava:
        with st.spinner("Hämtar källor och skapar den gemensamma utgåvan..."):
            har_startansvar = False
            try:
                if not model:
                    raise RuntimeError("API-nyckel saknas")
                with utgavelager["lock"]:
                    if startnyckel not in utgavelager["pagar"]:
                        utgavelager["pagar"].add(startnyckel)
                        har_startansvar = True
                    nyhetsutgava = utgavelager["nyheter"].get(nyhetsnyckel)
                    redaktionell_utgava = utgavelager["redaktionellt"].get(
                        redaktionell_nyckel
                    )

                if not har_startansvar:
                    raise RuntimeError("Utgåvan skapas redan av en annan besökare")

                fasstatus = st.empty()
                if not nyhetsutgava:
                    fasstatus.markdown("**Steg 1 av 3:** Hämtar och kontrollerar nyhetskällor...")
                    starttid = time.perf_counter()
                    nyhetsdata, kallstatus, artiklar = hamta_kallmaterial(nyhetsnyckel)
                    rss_sekunder = time.perf_counter() - starttid
                    if not nyhetsdata:
                        hamta_kallmaterial.clear()
                        raise RuntimeError("Inga nyhetskällor kunde hämtas")

                    fasstatus.markdown("**Steg 2 av 3:** Skapar den korta nyhetsutgåvan...")
                    starttid = time.perf_counter()
                    nyhetstext = generera_nyhetsbriefing(nyhetsdata, nyhetsnyckel)
                    nyheter_ai_sekunder = time.perf_counter() - starttid
                    nyhetsutgava = {
                        "text": nyhetstext,
                        "rådata": nyhetsdata,
                        "artiklar": artiklar,
                        "kallstatus": kallstatus,
                        "prestanda": {
                            "rss_sekunder": rss_sekunder,
                            "nyheter_ai_sekunder": nyheter_ai_sekunder,
                            "antal_artiklar": len(artiklar),
                            "indatatecken": len(nyhetsdata),
                        },
                    }
                    with utgavelager["lock"]:
                        utgavelager["nyheter"].clear()
                        utgavelager["nyheter"][nyhetsnyckel] = nyhetsutgava
                        spara_utgavelager(utgavelager)

                if not redaktionell_utgava:
                    fasstatus.markdown("**Steg 3 av 3:** Skapar dagens böcker och morgontanke...")
                    starttid = time.perf_counter()
                    redaktionstext = generera_redaktionellt(redaktionell_nyckel)
                    if not redaktionstext:
                        raise RuntimeError("Redaktionellt innehåll kunde inte skapas")
                    redaktionell_utgava = {
                        "text": redaktionstext,
                        "prestanda": {
                            "redaktionellt_ai_sekunder": time.perf_counter() - starttid
                        },
                    }
                    with utgavelager["lock"]:
                        utgavelager["redaktionellt"].clear()
                        utgavelager["redaktionellt"][redaktionell_nyckel] = (
                            redaktionell_utgava
                        )
                        spara_utgavelager(utgavelager)
                fasstatus.empty()
                st.session_state.pop("startfel", None)
                st.rerun()
            except GeminiKvotSlut as error:
                logger.warning("Gemini-kvoten är slut för utgåva %s: %s", startnyckel, error)
                st.session_state["startfel"] = "kvot"
            except Exception as error:
                logger.exception("Kunde inte skapa utgåva %s: %s", startnyckel, error)
                st.session_state["startfel"] = "ovantat"
            finally:
                if har_startansvar:
                    with utgavelager["lock"]:
                        utgavelager["pagar"].discard(startnyckel)

if st.session_state.get("startfel") == "kvot":
    st.error(KVOTMEDDELANDE)
elif st.session_state.get("startfel"):
    st.error("Utgåvan kunde inte skapas just nu. Försök igen om en stund.")

if 'kallstatus' in st.session_state:
    visa_kallstatus(st.session_state['kallstatus'])

if st.session_state.get("prestanda"):
    with st.expander("Prestanda och resursanvändning"):
        prestanda = st.session_state["prestanda"]
        if "rss_sekunder" in prestanda:
            st.write(
                f"Källhämtning eller cacheläsning: **{prestanda['rss_sekunder']:.2f} sekunder**"
            )
        if "nyheter_ai_sekunder" in prestanda:
            st.write(
                "Nyhetsgenerering eller cacheläsning: "
                f"**{prestanda['nyheter_ai_sekunder']:.2f} sekunder**"
            )
        if "redaktionellt_ai_sekunder" in prestanda:
            st.write(
                "Böcker och morgontanke eller cacheläsning: "
                f"**{prestanda['redaktionellt_ai_sekunder']:.2f} sekunder**"
            )
        if "fordjupning_sekunder" in prestanda:
            st.write(f"Senaste fördjupning: **{prestanda['fordjupning_sekunder']:.2f} sekunder**")
        if "fraga_sekunder" in prestanda:
            st.write(f"Senaste assistentsvar: **{prestanda['fraga_sekunder']:.2f} sekunder**")
        st.write(f"Artiklar i underlaget: **{prestanda.get('antal_artiklar', 0)}**")
        st.write(f"Rensad indatamängd: **{prestanda.get('indatatecken', 0):,} tecken**")
        if "utdataord" in prestanda:
            st.write(f"Briefingens längd: **{prestanda['utdataord']:,} ord**")

# Visa briefing om den finns i minnet
if 'briefing' in st.session_state:
    st.markdown("---")
    visa_briefing(
        st.session_state['briefing'],
        st.session_state.get("artiklar", []),
    )

    # Interaktiv AI-chatt för begrepp, utökning och specifika nyheter
    st.markdown("---")
    st.subheader("💬 AI-assistent för dina frågor")
    st.write("Välj ett avsnitt så skickas bara den relevanta texten och dess källor till assistenten.")

    tillgangliga_sektioner = dela_upp_briefing(st.session_state["briefing"])
    sektionsalternativ = ["Briefingens korta sammanfattningar"] + [
        rubrik for rubrik, _, _ in tillgangliga_sektioner
    ]

    with st.form("fraga_till_assistenten", clear_on_submit=True):
        vald_sektion = st.selectbox("Frågan gäller", sektionsalternativ)
        användar_fråga = st.text_area(
            "Vad funderar du på?",
            height=140,
            placeholder="Skriv din fråga här. Du kan skriva på flera rader.",
        )
        skicka_fråga = st.form_submit_button("Fråga AI-assistenten")

    if skicka_fråga and användar_fråga.strip():
        if not model:
            st.error("⚠️ API-nyckel saknas för att använda chatten.")
        else:
            with st.spinner("AI-assistenten funderar..."):
                if vald_sektion == sektionsalternativ[0]:
                    avsnitt = "\n".join(
                        f"{rubrik}: {sammanfattning}"
                        for rubrik, sammanfattning, _ in tillgangliga_sektioner
                    )
                    kallunderlag = ""
                else:
                    rubrik, sammanfattning, innehall = next(
                        sektion for sektion in tillgangliga_sektioner if sektion[0] == vald_sektion
                    )
                    avsnitt = f"{rubrik}\n{sammanfattning}\n{innehall}"
                    kallunderlag = valj_kallunderlag(
                        innehall,
                        st.session_state.get("artiklar", []),
                    )
                starttid = time.perf_counter()
                try:
                    svar = svara_pa_fraga(användar_fråga, avsnitt, kallunderlag)
                    st.session_state["prestanda"]["fraga_sekunder"] = time.perf_counter() - starttid
                    st.info(svar)
                except GeminiKvotSlut:
                    st.error(KVOTMEDDELANDE)
                except Exception:
                    st.error("Assistenten kunde inte svara just nu. Försök igen senare.")
