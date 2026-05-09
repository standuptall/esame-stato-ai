import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import json
import random

# 1. Configurazione della pagina (Responsive per Mobile)
st.set_page_config(
    page_title="Preparatore Esame di Stato",
    page_icon="🎓",
    layout="centered"
)

# 2. Configurazione delle API (Recuperate in sicurezza dai Secrets di Streamlit)
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# 3. Connessione a Google Sheets
# Utilizza la libreria nativa di Streamlit per leggere/scrivere sul foglio Google
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl="0") # ttl=0 forza la lettura dei dati in tempo reale
except Exception as e:
    st.error("Errore di connessione al database Google Sheets. Verifica le credenziali.")
    st.stop()

# 4. Selezione del Quesito (Interfaccia Mobile-Friendly)
st.title("🎓 Preparatore Esame di Stato")
st.write("Il programma estrae automaticamente un quesito, dando priorità agli argomenti meno studiati.")

# Calcolo dei pesi: più bassa è la percentuale (o assente), maggiore è la priorità
percentuali = (
    df["Percentuale sicurezza"]
    .astype(str)
    .str.replace("%", "", regex=False)
    .str.replace(",", ".", regex=False)
    .str.strip()
    .replace("nan", "0")
    .astype(float)
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
if str(riga_corrente["Risoluzione"]) != "nan":
    with st.expander("Visualizza risoluzione registrata"):
        st.write(riga_corrente["Risoluzione"])

st.markdown("---")

# 5. Area di Interazione / Risoluzione
st.markdown("### La tua proposta di risoluzione:")
risposta_utente = st.text_area(
    "Inserisci qui i tuoi passaggi logici, formule o considerazioni normative:",
    height=200,
    placeholder="Scrivi qui come risolveresti il quesito..."
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
            
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt_docente)
            
            # Parsing della risposta (cercando il JSON all'interno del testo generato)
            try:
                # Estrazione del JSON
                testo_risposta = response.text
                inizio_json = testo_risposta.find("{")
                fine_json = testo_risposta.rfind("}") + 1
                dati_valutazione = json.loads(testo_risposta[inizio_json:fine_json])
                
                # Mostra la valutazione a schermo
                st.subheader("Valutazione del Docente:")
                st.write(dati_valutazione['valutazione_testo'])
                
                # Aggiornamento dei dati locali
                nuova_percentuale = dati_valutazione['nuova_percentuale']
                risoluzione_corretta = dati_valutazione['risoluzione_sintetica']
                
                # Scrittura su Google Sheets
                df.at[indice_riga, "Percentuale sicurezza"] = nuova_percentuale
                df.at[indice_riga, "Risoluzione"] = risoluzione_corretta
                
                # Salvataggio tramite la connessione
                conn.update(data=df)
                
                st.success(f"Aggiornamento completato! Nuova percentuale di sicurezza registrata sul foglio: {nuova_percentuale}%")
                
            except Exception as e:
                # Fallback nel caso in cui l'IA non formatti correttamente il JSON
                st.warning("La valutazione è stata generata, ma non è stato possibile aggiornare automaticamente il database.")
                st.write(response.text)