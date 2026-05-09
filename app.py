import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from google import genai
import json
import random
import time
import pandas as pd
import base64

# 1. Configurazione della pagina (Responsive per Mobile)
st.set_page_config(
    page_title="Preparatore Esame di Stato",
    page_icon="🎓",
    layout="centered"
)

# 2. Configurazione delle API (Recuperate in sicurezza dai Secrets di Streamlit)
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# 3. Connessione a Google Sheets tramite gspread
try:
    private_key_b64 = st.secrets["connections"]["gsheets"]["private_key_base64"]
    # Decodifica robusta: strip whitespace dal base64, normalizza newline e BOM
    decoded = base64.b64decode(private_key_b64.strip()).decode("utf-8")
    private_key_pem = decoded.replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n").strip()
    
    credenziali_dict = {
        "type": "service_account",
        "project_id": st.secrets["connections"]["gsheets"]["project_id"],
        "private_key_id": st.secrets["connections"]["gsheets"]["private_key_id"],
        "private_key": private_key_pem,
        "client_email": st.secrets["connections"]["gsheets"]["client_email"],
        "client_id": st.secrets["connections"]["gsheets"]["client_id"],
        "auth_uri": st.secrets["connections"]["gsheets"]["auth_uri"],
        "token_uri": st.secrets["connections"]["gsheets"]["token_uri"],
        "auth_provider_x509_cert_url": st.secrets["connections"]["gsheets"]["auth_provider_x509_cert_url"],
        "client_x509_cert_url": st.secrets["connections"]["gsheets"]["client_x509_cert_url"]
    }
    
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(credenziali_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    
    url_foglio = st.secrets["connections"]["gsheets"]["spreadsheet"]
    worksheet = gc.open_by_url(url_foglio).get_worksheet(0)
    
    df = pd.DataFrame(worksheet.get_all_records())
    
    # Sanitizzazione dei dati in lettura
    df["Percentuale sicurezza"] = pd.to_numeric(df["Percentuale sicurezza"], errors="coerce")
    df["Percentuale sicurezza"] = df["Percentuale sicurezza"].fillna(0).astype(int)
    
except Exception as e:
    st.write(str(e))
    st.error("Errore di connessione al database Google Sheets. Verifica le credenziali.")
    st.stop()

# 4. Selezione del Quesito (Interfaccia Mobile-Friendly)
st.title("🎓 Preparatore Esame di Stato")
st.write("Il programma estrae automaticamente un quesito, dando priorità agli argomenti meno studiati.")

# Calcolo dei pesi per l'estrazione pesata
percentuali = (
    df["Percentuale sicurezza"]
    .astype(str)
    .str.replace("%", "", regex=False)
    .str.replace(",", ".", regex=False)
    .str.strip()
    .replace("nan", "0")
    .replace("", "0")
    .astype(float)
    .fillna(0)
    .clip(0, 100)
)
pesi = (100 - percentuali + 1).tolist()  # peso minimo 1 (100%), massimo 101 (0%/NaN)

def estrai_quesito():
    st.session_state.indice_quesito = random.choices(range(len(df)), weights=pesi, k=1)[0]

if "indice_quesito" not in st.session_state:
    estrai_quesito()

st.button("🎲 Estrai un nuovo quesito", on_click=estrai_quesito, use_container_width=True)

# Recupero della riga corrispondente
indice_riga = st.session_state.indice_quesito
riga_corrente = df.iloc[indice_riga]

# Box informativo sullo stato attuale
col1, col2 = st.columns(2)
with col1:
    st.metric(label="Sicurezza Attuale", value=f"{riga_corrente['Percentuale sicurezza']}%")
with col2:
    st.info(f"Ambito: {riga_corrente.get('Ambito', 'Generale')}")

st.markdown("### Testo del Quesito:")
st.info(riga_corrente["Quesito"])

# Mostra la risoluzione precedentemente salvata (se esiste)
if str(riga_corrente["Risoluzione"]) != "nan" and str(riga_corrente["Risoluzione"]).strip() != "":
    with st.expander("Visualizza risoluzione registrata"):
        st.write(riga_corrente["Risoluzione"])

st.markdown("---")

# 5. Area di Interazione / Risoluzione
st.markdown("### La tua proposta di risoluzione:")
risposta_utente = st.text_area(
    "Inserisci qui i tuoi passaggi logici, formule o considerazioni normative:",
    height=200,
    placeholder="Scrivi qui come risolveresti il quesito...",
    key="risposta_utente_input"
)

if st.button("Sottoponi all'Agente", use_container_width=True):
    if not risposta_utente:
        st.warning("Inserisci una risposta prima di inviare.")
    else:
        with st.spinner("Il docente sta valutando la tua risposta..."):
            
            # Prompt di sistema strutturato per ottenere un output deterministico (JSON) alla fine
            prompt_docente = f"""
            Sei un severo Professore Universitario e Presidente della Commissione per l'Abilitazione alla professione di Ingegnere.
            Valuta la risposta del candidato al seguente quesito.
            
            Quesito: {riga_corrente['Quesito']}
            Risposta del candidato: {risposta_utente}
            
            Fornisci una valutazione dettagliata, accademica e rigorosa, evidenziando errori teorici, mancanze normative o imprecisioni logiche.
            Alla fine della tua valutazione, assegna una nuova 'Percentuale di sicurezza' (un valore intero tra 0 e 100) basandoti sulla qualità della risposta.
            Inoltre, redigi una sintesi strutturata della 'Risoluzione ideale' che il candidato dovrebbe tenere a mente.
            
            DEVI formattare la parte finale della tua risposta come un blocco JSON valido con le seguenti chiavi:
            - 'valutazione_testo': (la tua spiegazione accademica dettagliata)
            - 'nuova_percentuale': (il valore numerico intero)
            - 'risoluzione_sintetica': (la sintesi della risoluzione corretta)
            """
            
            response = None
            for attempt in range(3):
                try:
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt_docente
                    )
                    break
                except Exception as e:
                    # Riconosce l'errore di quota esaurita analizzando la stringa dell'errore
                    errore_str = str(e)
                    if "429" in errore_str or "ResourceExhausted" in errore_str or "exhausted" in errore_str.lower():
                        if attempt < 2:
                            wait = 30 * (attempt + 1)
                            st.warning(f"Limite di richieste API raggiunto. Riprovo tra {wait} secondi...")
                            time.sleep(wait)
                        else:
                            st.error("Quota API esaurita. Attendi qualche minuto e riprova.")
                            st.stop()
                    else:
                        st.error(f"Si è verificato un errore imprevisto con le API di Google: {e}")
                        st.stop()
            
            # Parsing della risposta (cercando il JSON all'interno del testo generato)
            if response:
                try:
                    # Estrazione del JSON
                    testo_risposta = response.text
                    inizio_json = testo_risposta.find("{")
                    fine_json = testo_risposta.rfind("}") + 1
                    dati_valutazione = json.loads(testo_risposta[inizio_json:fine_json])
                    
                    # Mostra la valutazione a schermo
                    st.subheader("Valutazione del Docente:")
                    st.write(dati_valutazione['valutazione_testo'])
                    
                    # Recupero dati per l'aggiornamento
                    nuova_percentuale = dati_valutazione['nuova_percentuale']
                    risoluzione_corretta = dati_valutazione['risoluzione_sintetica']
                    
                    # Aggiornamento diretto delle celle nel foglio Google
                    intestazioni = df.columns.tolist()
                    col_perc = intestazioni.index("Percentuale sicurezza") + 1
                    col_risol = intestazioni.index("Risoluzione") + 1
                    riga_sheet = indice_riga + 2  # +1 per header, +1 per indice 1-based
                    worksheet.update_cell(riga_sheet, col_perc, nuova_percentuale)
                    worksheet.update_cell(riga_sheet, col_risol, str(risoluzione_corretta))
                    
                    st.success(f"Aggiornamento completato! Nuova percentuale di sicurezza registrata sul foglio: {nuova_percentuale}%")
                    
                except Exception as e:
                    # Fallback nel caso in cui l'IA non formatti correttamente il JSON o ci sia un errore di rete
                    st.warning("La valutazione è stata generata, ma non è stato possibile aggiornare automaticamente il database.")
                    st.write(str(e))
                    st.write(response.text)