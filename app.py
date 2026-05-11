import streamlit as st
from google import genai
import json
import random
import time
import pandas as pd
import os
import io

# 1. Configurazione della pagina (Responsive per Mobile)
st.set_page_config(
    page_title="Preparatore Esame di Stato",
    page_icon="🎓",
    layout="centered"
)

# 2. Configurazione delle API
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# 3. Caricamento dati da file Excel locale
CSV_PATH = os.path.join(os.path.dirname(__file__), "quesiti.xlsx")

def carica_dati():
    df = pd.read_excel(CSV_PATH, dtype={"Percentuale sicurezza": float})
    df["Percentuale sicurezza"] = df["Percentuale sicurezza"].fillna(0).astype(int)
    df["Risoluzione"] = df["Risoluzione"].fillna("")
    return df

def salva_dati(df):
    df.to_excel(CSV_PATH, index=False)

def sanitize_json_string(s):
    """Escape control characters inside JSON string values to prevent parse errors."""
    result = []
    in_string = False
    escape_next = False
    for char in s:
        if escape_next:
            result.append(char)
            escape_next = False
        elif char == '\\' and in_string:
            result.append(char)
            escape_next = True
        elif char == '"':
            in_string = not in_string
            result.append(char)
        elif in_string and ord(char) < 0x20:
            if char == '\n':
                result.append('\\n')
            elif char == '\r':
                result.append('\\r')
            elif char == '\t':
                result.append('\\t')
            else:
                result.append('\\u{:04x}'.format(ord(char)))
        else:
            result.append(char)
    return ''.join(result)

df = carica_dati()

# Sidebar: download CSV aggiornato
with st.sidebar:
    st.markdown("### 📥 Esporta dati")
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    st.download_button(
        label="Scarica quesiti.xlsx aggiornato",
        data=buffer,
        file_name="quesiti.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# 4. Selezione del Quesito (Interfaccia Mobile-Friendly)
st.title("🎓 Preparatore Esame di Stato")
st.write("Il programma estrae automaticamente un quesito, dando priorità agli argomenti meno studiati.")

# Calcolo dei pesi per l'estrazione pesata
percentuali = df["Percentuale sicurezza"].clip(0, 100)
pesi = (100 - percentuali + 1).tolist()  # peso minimo 1 (100%), massimo 101 (0%)

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
if str(riga_corrente["Risoluzione"]).strip() not in ("", "nan"):
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

            prompt_docente = f"""
            Sei un stimato Professore Universitario e Membro della Commissione per l'Abilitazione alla professione di Ingegnere.
            Il tuo compito è valutare la risposta del candidato in modo rigoroso, professionale ed equo. Non essere inutilmente distruttivo, ma premia la logica ingegneristica.
            
            Quesito: {riga_corrente['Quesito']}
            Risposta del candidato: {risposta_utente}
            
            LINEE GUIDA PER LA VALUTAZIONE:
            1. Analizza la risposta evidenziando gli aspetti corretti (passaggi logici ben strutturati, richiami normativi pertinenti, formule adeguate).
            2. Segnala con precisione scientifica le lacune, le imprecisioni o le omissioni importanti.
            3. Adotta un tono accademico, formale ma costruttivo (fornisci suggerimenti su come migliorare l'esposizione).
            
            SCALA DI ASSEGNAZIONE DELLA 'PERCENTUALE DI SICUREZZA' (Sii equilibrato!):
            - 90-100%: Risposta eccellente, completa, rigorosa e priva di errori sostanziali.
            - 70-89%: Buona risposta, individua i punti chiave ma presenta lievi imprecisioni o manca di qualche dettaglio secondario.
            - 50-69%: Risposta sufficiente/discreta, dimostra di conoscere l'argomento a grandi linee ma pecca di superficialità o tralascia aspetti importanti.
            - 30-49%: Risposta insufficiente, concetti confusi o gravi lacune teoriche/normative.
            - 1-29%: Risposta gravemente insufficiente o quasi del tutto fuori tema.
            - 0%: Solo ed esclusivamente se la risposta è totalmente vuota, copiata, o del tutto priva di senso (es. parole singole casuali come 'test').
            
            DEVI formattare la parte finale della tua risposta come un blocco JSON valido con le seguenti chiavi:
            - 'valutazione_testo': (la tua spiegazione accademica dettagliata e costruttiva)
            - 'nuova_percentuale': (il valore numerico intero basato sulla scala sopra descritta)
            - 'risoluzione_sintetica': (la sintesi della risoluzione ideale/corretta)
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

            if response:
                try:
                    testo_risposta = response.text
                    inizio_json = testo_risposta.find("{")
                    fine_json = testo_risposta.rfind("}") + 1
                    json_str = sanitize_json_string(testo_risposta[inizio_json:fine_json])
                    dati_valutazione = json.loads(json_str)

                    st.subheader("Valutazione del Docente:")
                    st.write(dati_valutazione['valutazione_testo'])

                    nuova_percentuale = int(dati_valutazione['nuova_percentuale'])
                    risoluzione_corretta = dati_valutazione['risoluzione_sintetica']

                    # Aggiornamento e salvataggio nel CSV
                    df.at[indice_riga, "Percentuale sicurezza"] = nuova_percentuale
                    df.at[indice_riga, "Risoluzione"] = risoluzione_corretta
                    salva_dati(df)

                    st.success(f"Aggiornamento completato! Nuova percentuale di sicurezza: {nuova_percentuale}%")

                except Exception as e:
                    st.warning("La valutazione è stata generata, ma non è stato possibile aggiornare il database.")
                    st.write(str(e))
                    if response:
                        st.write(response.text)
