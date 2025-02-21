import streamlit as st
import requests
import base64
import os
from dotenv import load_dotenv
from create_invoice_excel import create_excel_from_data, load_invoice_data
from google.cloud import storage

# Charger les variables d'environnement depuis .env
load_dotenv()

# Configuration de l'API endpoint
API_URL = os.getenv("API_URL", "http://fastapi:8000")

# Initialiser le client Storage
storage_client = storage.Client()
PROJECT_ID = os.getenv("PROJECT_ID", "nomadsfacturation")
bucket_name = f"{PROJECT_ID}-temp-files"
bucket = storage_client.bucket(bucket_name)

st.set_page_config(
    page_title="Analyse de Factures PDF",
    page_icon="📊",
    layout="centered"
)

# Centrer le titre Nomads Surfing
st.markdown("<h1 style='text-align: center;'>Nomads Surfing 🌊</h1>", unsafe_allow_html=True)

# Centrer le sous-titre sur une seule ligne
st.markdown("<h2 style='text-align: center;'>Analyse automatique de factures PDF</h2>", unsafe_allow_html=True)

# Upload multiple PDF files
uploaded_files = st.file_uploader(" ", type="pdf", accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        st.write("📄 Fichier chargé :", uploaded_file.name)

    # Bouton pour lancer l'analyse
    if st.button("Analyser"):
        try:
            with st.spinner("🔄 Analyse en cours..."):
                # Préparer les fichiers pour l'envoi
                files = [("files", (file.name, file.getvalue(), "application/pdf")) for file in uploaded_files]

                # Envoyer tous les fichiers en une seule requête
                response = requests.post(f"{API_URL}/analyze_pdfs/", files=files, timeout=60)

                if response.status_code == 200:
                    st.success("✅ Analyse des documents terminée avec succès ! 🎉")

                    # Extraire le nom du fichier Excel depuis les headers
                    content_disposition = response.headers.get('Content-Disposition', '')
                    filename = content_disposition.split('filename=')[-1].strip('"') if 'filename=' in content_disposition else "recapitulatif.xlsx"

                    try:
                        # Créer le dossier temp_files s'il n'existe pas
                        os.makedirs('temp_files', exist_ok=True)

                        # Sauvegarder dans le dossier temp_files
                        file_path = os.path.join('temp_files', filename)

                        with open(file_path, "wb") as f:
                            f.write(response.content)

                        st.success(f"📂 Fichier Excel créé avec succès ! 🤙")

                        # Proposer le téléchargement via Streamlit
                        blob = bucket.blob(filename)
                        blob.upload_from_string(response.content)

                        # Pour le téléchargement
                        blob = bucket.blob(filename)
                        file_content = blob.download_as_bytes()
                        st.download_button(
                            label=f"📎 Télécharger {filename}",
                            data=file_content,
                            file_name=filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

                    except Exception as e:
                        st.error(f"❌ Erreur lors de la sauvegarde : {str(e)}")
                        # Proposer le téléchargement direct en cas d'erreur
                        st.download_button(
                            label=f"📎 Télécharger {filename}",
                            data=response.content,
                            file_name=filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

                else:
                    try:
                        error_detail = response.json().get('detail', 'Pas de détail disponible')
                        st.error(f"❌ Erreur lors de l'analyse (Status {response.status_code}): {error_detail}")
                    except:
                        st.error(f"❌ Erreur inconnue. Status code: {response.status_code}")

        except requests.exceptions.ConnectionError:
            st.error("⚠ Impossible de se connecter à l'API. Vérifiez que le serveur FastAPI tourne bien sur le port 8000.")
        except requests.exceptions.Timeout:
            st.error("⏳ Le serveur met trop de temps à répondre. Réessayez plus tard.")
        except Exception as e:
            st.error(f"🚨 Une erreur est survenue : {str(e)}")

def process_and_create_excel():
    """Fonction simple qui utilise create_excel_from_data"""
    try:
        # Charger les données
        invoices_data = load_invoice_data()

        # Utiliser directement la fonction de create_invoice_excel.py
        excel_path = create_excel_from_data(invoices_data)

        # Lire le fichier Excel créé
        with open(excel_path, 'rb') as f:
            excel_data = f.read()

        return excel_data, excel_path.name

    except Exception as e:
        st.error(f"Erreur lors de la création de l'Excel : {str(e)}")
        return None, None
