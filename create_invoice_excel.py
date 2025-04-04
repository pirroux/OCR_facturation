import pandas as pd
from datetime import datetime
import json
import re
import pytz  # Pour gérer les fuseaux horaires
from pathlib import Path
from openpyxl import Workbook
import os
from pdf_extractor import extract_text_from_pdf
from data_extractor import extract_data

def process_pdf_files():
    """Traite tous les PDF dans le folder et génère factures.json"""
    pdf_folder = Path("data_factures/facturesv3")
    output_file = Path("factures.json")

    # Vérifier si le dossier existe
    if not pdf_folder.exists():
        print(f"Le dossier {pdf_folder} n'existe pas.")
        return {}

    # Dictionnaire pour stocker toutes les factures
    all_invoices = {}

    # Traiter chaque PDF
    for pdf_path in pdf_folder.glob("*.pdf"):
        try:
            print(f"\nTraitement de {pdf_path.name}...")

            # Extraire le texte de chaque page
            pages_text = extract_text_from_pdf(str(pdf_path))
            if not pages_text:
                raise ValueError("Pas de texte extrait")

            # Nous allons regrouper les pages en factures
            current_invoice_pages = []
            current_invoice_num = None

            # Parcourir chaque page
            for page_idx, text in enumerate(pages_text):
                if not text.strip():
                    print(f"Page {page_idx + 1} vide, ignorée")
                    continue

                # Vérifier s'il s'agit d'une nouvelle facture ou d'une page supplémentaire
                is_new_invoice = True

                # Chercher le numéro de facture sur cette page
                fac_match_meg = re.search(r'N°\s*:\s*([A-Z0-9]+)', text)
                fac_match_internet = re.search(r'N° de facture\s*:\s*([^\n]+)', text)

                page_invoice_num = None
                if fac_match_meg:
                    page_invoice_num = fac_match_meg.group(1).strip()
                elif fac_match_internet:
                    page_invoice_num = fac_match_internet.group(1).strip()

                # Si on a un numéro de facture et qu'il est identique au numéro courant,
                # alors c'est une page supplémentaire de la facture courante
                if current_invoice_num and page_invoice_num and current_invoice_num == page_invoice_num:
                    is_new_invoice = False
                    current_invoice_pages.append(text)
                    print(f"Page {page_idx + 1} : continuation de la facture {current_invoice_num}")
                else:
                    # Si on a des pages accumulées, traiter la facture précédente
                    if current_invoice_pages:
                        process_invoice_pages(pdf_path.name, current_invoice_num, current_invoice_pages, all_invoices)

                    # Commencer une nouvelle facture
                    current_invoice_pages = [text]
                    current_invoice_num = page_invoice_num
                    print(f"Page {page_idx + 1} : nouvelle facture {current_invoice_num}")

            # Traiter la dernière facture si nécessaire
            if current_invoice_pages:
                process_invoice_pages(pdf_path.name, current_invoice_num, current_invoice_pages, all_invoices)

        except Exception as e:
            print(f"✗ Erreur sur {pdf_path.name}: {str(e)}")
            # Ajouter une entrée avec une structure minimale même en cas d'erreur
            all_invoices[pdf_path.name] = {
                'text': '',
                'data': {
                    'type': 'unknown',
                    'articles': [],
                    'TOTAL': {
                        'total_ht': 0,
                        'total_ttc': 0,
                        'tva': 0,
                        'remise': 0
                    },
                    'client_name': '',
                    'numero_facture': '',
                    'date_facture': '',
                    'date_commande': '',
                    'commentaire': '',
                    'Type_Vente': '',
                    'Réseau_Vente': '',
                    'nombre_articles': 0
                },
                'error': str(e)
            }

    # Sauvegarder toutes les factures dans un seul fichier JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_invoices, f, ensure_ascii=False, indent=2)

    print(f"\nToutes les factures ont été sauvegardées dans {output_file} ({len(all_invoices)} factures au total)")
    return all_invoices

def process_invoice_pages(pdf_name, invoice_num, pages_text, all_invoices):
    """Traite un ensemble de pages appartenant à une même facture"""
    # Fusionner le texte de toutes les pages
    combined_text = "\n\n".join(pages_text)

    # Déterminer le type de facture
    is_internet = "UGS" in combined_text
    is_acompte = "Facture d'acompte" in combined_text

    if is_internet:
        facture_type = "internet"
    elif is_acompte:
        facture_type = "acompte"
    else:
        facture_type = "meg"

    print(f"Type de facture détecté: {facture_type}")

    # Structure de base pour les données
    data = {
        'type': facture_type,
        'articles': [],
        'TOTAL': {
            'total_ht': 0,
            'total_ttc': 0,
            'tva': 0,
            'remise': 0
        },
        'client_name': '',
        'numero_facture': '',
        'date_facture': '',
        'date_commande': '',
        'commentaire': '',
        'Type_Vente': '',
        'Réseau_Vente': '',
        'nombre_articles': 0
    }

    # Essayer d'extraire plus de données si possible
    try:
        extracted_data = extract_data(combined_text, facture_type)
        # Fusionner les données extraites avec la structure de base
        for key, value in extracted_data.items():
            data[key] = value
    except Exception as e:
        print(f"Erreur lors de l'extraction des données détaillées: {str(e)}")

    # Créer une clé unique pour cette facture
    invoice_key = f"{pdf_name}_{invoice_num}" if invoice_num else f"{pdf_name}"

    # Ajouter au dictionnaire principal
    all_invoices[invoice_key] = {
        'text': combined_text,
        'data': data
    }

    print(f"✓ {invoice_key} traité avec succès ({len(pages_text)} pages)")

def load_invoice_data():
    """Charge les données des factures depuis le fichier JSON ou régénère le fichier si nécessaire"""
    try:
        # Option pour forcer la régénération du fichier
        force_regenerate = True

        if force_regenerate:
            print("Régénération forcée du fichier factures.json...")
            # Supprimer le fichier existant s'il existe
            json_path = Path('factures.json')
            if json_path.exists():
                json_path.unlink()
            # Générer un nouveau fichier
            return process_pdf_files()

        # Si on ne force pas la régénération, essayer de charger le fichier existant
        with open('factures.json', 'r', encoding='utf-8') as f:
            invoices_data = json.load(f)

            # Vérifier et corriger la structure des données
            for filename, invoice in invoices_data.items():
                if 'data' not in invoice:
                    print(f"Clé 'data' manquante pour {filename}, ajout d'une structure par défaut")
                    invoices_data[filename]['data'] = {
                        'type': 'unknown',
                        'articles': [],
                        'TOTAL': {
                            'total_ht': 0,
                            'total_ttc': 0,
                            'tva': 0,
                            'remise': 0
                        },
                        'client_name': '',
                        'numero_facture': '',
                        'date_facture': '',
                        'date_commande': '',
                        'commentaire': '',
                        'Type_Vente': '',
                        'Réseau_Vente': '',
                        'nombre_articles': 0
                    }

            # Calculer le nombre total d'articles pour chaque facture
            for invoice in invoices_data.values():
                articles = invoice['data'].get('articles', [])
                total_quantity = sum(article.get('quantite', 0) for article in articles)
                invoice['data']['nombre_articles'] = total_quantity

            return invoices_data
    except FileNotFoundError:
        print("Erreur: Le fichier factures.json n'a pas été trouvé")
        # Essayer de générer le fichier
        return process_pdf_files()
    except json.JSONDecodeError:
        print("Erreur: Le fichier factures.json n'est pas un JSON valide")
        return process_pdf_files()
    except Exception as e:
        print(f"Erreur lors du chargement des données: {str(e)}")
        return process_pdf_files()

def save_invoice_data(invoices_data):
    """Sauvegarde les données des factures dans le fichier JSON"""
    try:
        with open('factures.json', 'w', encoding='utf-8') as f:
            json.dump(invoices_data, f, ensure_ascii=False, indent=2)
        print("Factures sauvegardées avec succès.")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des factures: {str(e)}")

def format_date(date_str: str) -> str:
    """Convertit une date YYYY-MM-DD en DD/MM/YYYY"""
    if not date_str:
        return ''
    try:
        year, month, day = date_str.split('-')
        return f"{day}/{month}/{year}"
    except ValueError:
        return date_str

def create_invoice_dataframe(invoices_data):
    """Crée un DataFrame à partir des données des factures"""
    headers = [
        'Type-facture', 'n°ordre', 'saisie', 'Syst', 'N° Syst.', 'comptable', 'Type_facture',
        'Type_Vente', 'Réseau_Vente', 'Client', 'Typologie', 'Banque créditée',
        'Date commande', 'Date facture', 'Date expédition', 'Commentaire',
        'date1', 'acompte1', 'date2', 'acompte2', 'Date solde', 'solde',
        'contrôle paiement', 'reste dû', 'AVO', 'tva', 'ttc', 'Credit TTC',
        'Credit HT', 'remise', 'TVA Collectee', 'quantité'
    ]

    # Ajouter les headers pour les articles
    for i in range(1, 21):
        headers.extend([f'supfam{i}', f'fam{i}', f'ref{i}', f'q{i}', f'prix{i}',
                      f'r€{i}', f'ht{i}', f'tva€{i}'])

    rows = []

    # Vérifier si invoices_data est vide
    if not invoices_data:
        # Retourner un DataFrame vide avec les bonnes colonnes
        return pd.DataFrame(columns=headers)

    for filename, invoice in invoices_data.items():
        try:
            # Vérifier si 'data' existe dans invoice
            if 'data' not in invoice:
                print(f"Clé 'data' manquante pour {filename}")
                continue

            data = invoice['data']
            row = {col: '' for col in headers}  # Initialiser toutes les colonnes avec des valeurs vides

            # Calculer la quantité totale - somme des quantités de tous les articles
            articles = data.get('articles', [])
            total_quantity = sum(float(article.get('quantite', 0)) for article in articles)
            row['quantité'] = total_quantity  # Mettre à jour la colonne 'quantité'
            print(f"Quantité totale pour {filename}: {total_quantity}")

            # Extraire la date
            date = data.get('date', '')
            if data.get('type') == 'internet' and 'text' in invoice:
                date_match = re.search(r'Date de commande\s*:\s*(\d{1,2}\s*\w+\s*\d{4})', invoice.get('text', ''))
                if date_match:
                    date_fr = date_match.group(1).strip()
                    mois_fr = {
                        'janvier': '01', 'février': '02', 'mars': '03', 'avril': '04',
                        'mai': '05', 'juin': '06', 'juillet': '07', 'août': '08',
                        'septembre': '09', 'octobre': '10', 'novembre': '11', 'décembre': '12'
                    }
                    for mois, num in mois_fr.items():
                        date_fr = date_fr.replace(mois, num)
                    try:
                        jour, mois, annee = re.match(r'(\d{1,2})\s*(\d{2})\s*(\d{4})', date_fr).groups()
                        date = f"{annee}-{mois}-{jour.zfill(2)}"
                    except (AttributeError, ValueError):
                        date = ''

            # Extraire les informations d'acompte
            acompte_match = None
            if 'text' in invoice:
                acompte_match = re.search(r'Echéance\(s\)\s*Acompte\s*de\s*(\d+[\s\d]*,\d+)\s*€\s*au\s*(\d{2}/\d{2}/\d{4})', invoice.get('text', ''))

            montant_acompte = ''
            date_acompte_iso = ''
            if acompte_match:
                montant_acompte = float(acompte_match.group(1).replace(' ', '').replace(',', '.'))
                date_acompte = acompte_match.group(2)
                jour, mois, annee = date_acompte.split('/')
                date_acompte_iso = f"{annee}-{mois}-{jour}"

            # Calculer le taux de TVA et le total HT avec remise
            total_ht = data.get('TOTAL', {}).get('total_ht', 0)
            remise = data.get('TOTAL', {}).get('remise', 0)

            # Extraire explicitement la remise pour toutes les factures
            if 'text' in invoice:
                # Rechercher la remise dans le texte
                remise_patterns = [
                    r'Remise\s+(?:globale|totale)?\s*:?\s*(\d+[\s\d]*[,.]\d+)\s*€',
                    r'Remise\s+(\d+[\s\d]*[,.]\d+)\s*%',
                    r'Remise\s+(?:totale)?\s*:?\s*(\d+[\s\d]*[,.]\d+)',
                ]

                for pattern in remise_patterns:
                    remise_match = re.search(pattern, invoice.get('text', ''), re.IGNORECASE)
                    if remise_match:
                        remise_value = remise_match.group(1).replace(' ', '').replace(',', '.')
                        if '%' in pattern:
                            # Si c'est un pourcentage, calculer la valeur en euros
                            remise_percent = float(remise_value)
                            remise = total_ht * (remise_percent / 100)
                        else:
                            remise = float(remise_value)
                        print(f"  Remise trouvée pour {filename}: {remise} €")
                        break

            # Appliquer la remise si elle existe
            if remise:
                total_ht_avec_remise = total_ht - float(remise)
                row['remise'] = remise  # Écrire la remise globale dans la colonne dédiée
            else:
                total_ht_avec_remise = total_ht
                row['remise'] = 0

            total_ttc = data.get('TOTAL', {}).get('total_ttc', 0)
            tva_value = data.get('TOTAL', {}).get('tva', 0)

            # S'assurer que total_ttc est correctement calculé pour les factures MEG
            if data.get('type') == 'meg' and total_ttc == 0 and total_ht > 0 and tva_value > 0:
                total_ttc = total_ht_avec_remise + tva_value
                print(f"  Total TTC calculé pour {filename}: {total_ttc}")

            taux_tva = ''
            taux_tva_decimal = 0.0
            if data.get('type') == 'meg' and articles:
                taux_tva_decimal = articles[0].get('tva', 0) / 100
                taux_tva = f"{articles[0].get('tva', 0):.2f}%".replace('.', ',')
            else:
                if total_ht and total_ht != 0:
                    taux_tva_decimal = (total_ttc / total_ht) - 1
                    taux_tva = f"{taux_tva_decimal * 100:.2f}%".replace('.', ',')
                else:
                    taux_tva_decimal = 0.2  # 20% par défaut
                    taux_tva = "20,00%"

            # Remplir les données dans l'ordre exact des colonnes
            row['Type-facture'] = " "
            row['n°ordre'] = " "
            row['saisie'] = ''
            if data.get('type') == 'meg':
                row['Syst'] = 'MEG'
            elif data.get('type') == 'internet':
                row['Syst'] = 'Internet'
            elif data.get('type') == 'acompte':
                row['Syst'] = 'Acompte'
            else:
                row['Syst'] = data.get('type', '')

            # Utiliser numéro de commande si numéro de facture n'est pas disponible
            if data.get('numero_facture'):
                row['N° Syst.'] = data.get('numero_facture', '')
            elif data.get('numero_commande'):
                row['N° Syst.'] = data.get('numero_commande', '')
            else:
                row['N° Syst.'] = ''

            row['comptable'] = ''

            # S'assurer que Type_facture, Type_Vente et Réseau_Vente sont correctement remplis
            if data.get('type') == 'meg':
                row['Type_facture'] = 'Facture'
            elif data.get('type') == 'acompte':
                row['Type_facture'] = 'Acompte'
            elif data.get('type') == 'internet':
                row['Type_facture'] = 'Internet'
            else:
                row['Type_facture'] = data.get('type', '')

            # Pour Type_Vente et Réseau_Vente, utiliser les valeurs directement depuis les données
            row['Type_Vente'] = data.get('Type_Vente', '')
            row['Réseau_Vente'] = data.get('Réseau_Vente', '')
            row['Client'] = data.get('client_name', '')
            row['Typologie'] = ''
            row['Banque créditée'] = ''
            row['Date commande'] = format_date(data.get('date_commande', ''))
            row['Date facture'] = format_date(data.get('date_facture', ''))
            row['Date expédition'] = ''
            row['Commentaire'] = data.get('commentaire', '')
            row['date1'] = format_date(date_acompte_iso)
            row['acompte1'] = montant_acompte
            row['date2'] = ''
            row['acompte2'] = ''
            row['Date solde'] = ''

            # S'assurer que le solde est correctement rempli
            if isinstance(total_ttc, (int, float)) and total_ttc > 0:
                row['solde'] = total_ttc
                print(f"Solde pour {filename}: {total_ttc}")
            else:
                # Si pas de total_ttc, essayer de le calculer à partir de total_ht et tva
                if total_ht_avec_remise > 0:
                    row['solde'] = total_ht_avec_remise + tva_value
                    print(f"Solde calculé pour {filename}: {row['solde']} (HT: {total_ht_avec_remise}, TVA: {tva_value})")
                else:
                    row['solde'] = 0
                    print(f"Attention: Pas de solde trouvé pour {filename}")

            row['contrôle paiement'] = data.get('statut_paiement', '')
            row['reste dû'] = data.get('TOTAL', {}).get('total_ttc', 0) - data.get('TOTAL', {}).get('total_ttc', 0)
            row['AVO'] = ''
            row['tva'] = taux_tva
            row['ttc'] = ''
            row['Credit TTC'] = total_ttc
            row['Credit HT'] = total_ht_avec_remise  # Utiliser le total HT avec remise
            row['TVA Collectee'] = tva_value

            # Remplir les articles
            article_index = 1
            for article in articles:
                if article_index > 20:
                    break

                # Récupérer les données de l'article
                quantite = float(article.get('quantite', 0))
                prix_unitaire = article.get('prix_unitaire', 0)
                montant_ht = article.get('montant_ht', 0)
                # Les remises individuelles d'articles ne sont plus utilisées
                # pour la colonne "r€N" car la remise est appliquée au total
                # article_remise = article.get('remise', 0)
                article_remise = 0  # Mettre à 0 pour les colonnes r€N

                # Traitement spécifique selon le type de facture
                if data.get('type') == 'meg':
                    # Pour MEG, calcul basé sur le taux de TVA de l'article
                    taux_tva_decimal_article = article.get('tva', 0) / 100
                    # ici prix_unitaire est déjà HT
                    tva_euros = montant_ht * taux_tva_decimal_article

                    # Pour les factures MEG, si une remise est détectée, calculer la valeur en euros basée sur le prix HT
                    if article.get('remise', 0) > 0:
                        remise_pourcentage = article.get('remise', 0)  # Déjà en décimal (exemple: 0.10 pour 10%)
                        article_remise = prix_unitaire * remise_pourcentage * quantite  # Remise en euros sur le montant HT
                        print(f"  MEG: Remise de {remise_pourcentage*100}% sur article {article.get('reference', '')}: {article_remise} € (calculée sur le prix HT {prix_unitaire} €)")

                        # Quand une remise est détectée, prix1 doit être montant_ht + tva_euros (somme exacte)
                        prix_pour_excel = (montant_ht + tva_euros) / quantite
                    else:
                        # Quand pas de remise, calcul standard
                        prix_unitaire_ttc = prix_unitaire * (1 + taux_tva_decimal_article)
                        prix_pour_excel = prix_unitaire_ttc

                    print(f"  MEG: prix unitaire HT={prix_unitaire}, TVA={taux_tva_decimal_article*100}%, prix affiché={prix_pour_excel}")

                else:  # internet ou acompte
                    # Pour Internet, le prix_unitaire stocké peut être HT ou TTC
                    # Pour les factures internet, le prix affiché est TTC et on doit calculer le HT en divisant par 1.20
                    if data.get('type') == 'internet':
                        # Pour les factures internet, nous avons maintenant directement le prix TTC extrait
                        # - prix1 est directement le prix TTC
                        # - ht1 est prix1/1.20
                        # - tva1 est la différence entre prix1 et ht1

                        # Utiliser le prix TTC extrait directement
                        if 'prix_ttc' in article:
                            prix_unitaire_ttc = article.get('prix_ttc', 0)
                        else:
                            # Calculer le prix TTC à partir du prix HT si non disponible
                            prix_unitaire_ttc = prix_unitaire * (1 + taux_tva_decimal)

                        # Le prix à afficher dans Excel est le prix TTC
                        prix_pour_excel = prix_unitaire_ttc

                        # Le montant HT est le prix TTC divisé par 1.20
                        prix_unitaire_ht = prix_unitaire_ttc / 1.20
                        montant_ht = prix_unitaire_ht * quantite

                        # La TVA est la différence entre le prix TTC et le HT
                        tva_euros = (prix_unitaire_ttc - prix_unitaire_ht) * quantite

                        print(f"  Article {article.get('reference', '')}: prix TTC={prix_unitaire_ttc}, HT={prix_unitaire_ht}, TVA={prix_unitaire_ttc - prix_unitaire_ht}")
                    else:  # acompte
                        # Pour les factures d'acompte, le calcul reste standard
                        # Calculer montant HT si non disponible
                        if montant_ht == 0 and prix_unitaire > 0:
                            montant_ht = prix_unitaire * quantite
                        elif prix_unitaire == 0 and montant_ht > 0 and quantite > 0:
                            prix_unitaire = montant_ht / quantite

                        prix_unitaire_ttc = prix_unitaire * (1 + taux_tva_decimal)
                        montant_ttc = montant_ht * (1 + taux_tva_decimal)
                        tva_euros = montant_ht * taux_tva_decimal
                        prix_pour_excel = prix_unitaire_ttc

                # S'assurer que prix unitaire et montant HT sont cohérents mais distincts
                if montant_ht == prix_unitaire and quantite > 1:
                    # Si les valeurs sont identiques alors que la quantité est > 1, c'est une erreur
                    prix_unitaire = montant_ht / quantite
                    prix_unitaire_ttc = prix_unitaire * (1 + taux_tva_decimal)
                    prix_pour_excel = prix_unitaire_ttc if data.get('type') == 'internet' else prix_unitaire
                    print(f"  Correction prix unitaire pour article {article_index} ({article.get('reference', '')}): {prix_pour_excel}")

                row[f'supfam{article_index}'] = ''
                row[f'fam{article_index}'] = ''
                row[f'ref{article_index}'] = article.get('reference', '')
                row[f'q{article_index}'] = quantite
                row[f'prix{article_index}'] = round(prix_pour_excel, 2)
                row[f'r€{article_index}'] = article_remise  # Remise spécifique à l'article
                row[f'ht{article_index}'] = round(montant_ht, 2)
                row[f'tva€{article_index}'] = round(tva_euros, 2)

                article_index += 1

            # Ajouter les frais d'expédition comme un article supplémentaire
            frais_expedition = data.get('frais_expedition', {})
            if frais_expedition and (frais_expedition.get('montant', 0) > 0 or frais_expedition.get('description', '')):
                if article_index <= 20:  # S'assurer qu'on n'a pas dépassé le nombre maximum d'articles
                    # Créer un nouvel article pour les frais d'expédition
                    if frais_expedition.get('montant', 0) > 0:
                        # Frais d'expédition payants
                        montant_ht = frais_expedition.get('montant', 0) / 1.20
                        prix_unitaire = montant_ht  # Prix HT
                        prix_unitaire_ttc = frais_expedition.get('montant', 0)  # Prix TTC
                        tva_euros = montant_ht * 0.20

                        print(f"  Ajout des frais d'expédition: {montant_ht:.2f} € HT ({prix_unitaire_ttc:.2f} € TTC) - {frais_expedition.get('description', 'Transport')}")
                    else:
                        # Transport gratuit
                        montant_ht = 0
                        prix_unitaire = 0
                        prix_unitaire_ttc = 0
                        tva_euros = 0

                        print(f"  Ajout du transport gratuit: {frais_expedition.get('description', 'Transport gratuit')}")

                    # Choisir le prix pour l'affichage selon le type de facture
                    prix_pour_excel = prix_unitaire_ttc if data.get('type') == 'internet' else prix_unitaire

                    # Remplir les données de l'article d'expédition dans le DataFrame
                    row[f'supfam{article_index}'] = frais_expedition.get('description', 'Transport')
                    row[f'fam{article_index}'] = ''
                    row[f'ref{article_index}'] = 'TRANSPORT'
                    row[f'q{article_index}'] = 1
                    row[f'prix{article_index}'] = round(prix_pour_excel, 2)
                    row[f'r€{article_index}'] = 0  # Pas de remise sur le transport
                    row[f'ht{article_index}'] = round(montant_ht, 2)
                    row[f'tva€{article_index}'] = round(tva_euros, 2)

            rows.append(row)

        except Exception as e:
            print(f"Erreur lors du traitement de {filename}: {str(e)}")
            continue

    # Si aucune ligne n'a été ajoutée, retourner un DataFrame vide avec les bonnes colonnes
    if not rows:
        return pd.DataFrame(columns=headers)

    # Créer le DataFrame en respectant l'ordre exact des colonnes
    df = pd.DataFrame(rows)

    # S'assurer que toutes les colonnes sont présentes, même si vides
    for col in headers:
        if col not in df.columns:
            df[col] = ''

    return df[headers]  # Forcer l'ordre exact des colonnes

def format_excel(writer, df):
    """Applique le formatage au fichier Excel"""
    try:
        workbook = writer.book
        worksheet = writer.sheets['Factures']

        # Définir la largeur des colonnes
        for idx, col in enumerate(df.columns):
            max_length = max(
                df[col].astype(str).apply(len).max(),
                len(str(col))
            ) + 2
            worksheet.set_column(idx, idx, max_length)

        # Créer des formats
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'bg_color': '#D9E1F2',
            'border': 1
        })

        # Appliquer le format aux en-têtes
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)

    except Exception as e:
        print(f"Erreur lors du formatage Excel: {str(e)}")

def create_excel_from_data(invoices_data):
    """Crée un fichier Excel à partir des données des factures"""
    # Initialiser le DataFrame
    rows = []

    for filename, invoice in invoices_data.items():
        try:
            # Les données sont dans invoice['data']['invoice_data']
            invoice_data = invoice.get('data', {}).get('invoice_data', {})

            # Accéder aux totaux via invoice_data
            totals = invoice_data.get('TOTAL', {})

            row = {
                'Type-facture': " ",
                'n°ordre': " ",
                'saisie': '',
                'Syst': 'MEG' if invoice_data.get('type') == 'meg' else 'Internet',
                'N° Syst.': invoice_data.get('numero_facture', ''),
                'comptable': '',
                'Type_facture': '',
                'Type_Vente': invoice_data.get('Type_Vente', ''),
                'Réseau_Vente': invoice_data.get('Réseau_Vente', ''),
                'Client': invoice_data.get('client_name', ''),
                'Total HT': totals.get('total_ht', 0),
                'Total TTC': totals.get('total_ttc', 0),
                'TVA': totals.get('tva', 0),
                'remise': totals.get('remise', 0)
            }
            rows.append(row)
        except Exception as e:
            print(f"Erreur lors du traitement de {filename}: {str(e)}")
            continue

    # Créer le DataFrame
    df = pd.DataFrame(rows)

    # Sauvegarder en Excel
    excel_path = "temp_files/factures.xlsx"
    df.to_excel(excel_path, index=False)

    # Save the updated invoices data to factures.json
    save_invoice_data(invoices_data)

    return Path(excel_path)

def main():
    try:
        # Charger les données
        invoices_data = load_invoice_data()
        if not invoices_data:
            print("Aucune donnée à traiter")
            return

        # Vérifier la structure des données
        for filename, invoice in invoices_data.items():
            if 'data' not in invoice:
                print(f"Clé 'data' manquante pour {filename}")
                # Ajouter une structure minimale
                invoices_data[filename]['data'] = {
                    'type': 'unknown',
                    'articles': [],
                    'TOTAL': {
                        'total_ht': 0,
                        'total_ttc': 0,
                        'tva': 0,
                        'remise': 0
                    },
                    'client_name': '',
                    'numero_facture': '',
                    'date_facture': '',
                    'date_commande': '',
                    'commentaire': '',
                    'Type_Vente': '',
                    'Réseau_Vente': '',
                    'nombre_articles': 0
                }

        # Créer le DataFrame
        df = create_invoice_dataframe(invoices_data)
        if df.empty:
            print("Aucune donnée valide à exporter")
            return

        # Générer le nom du fichier avec la date et l'heure au format YYMMDDHHMMSS en GMT+1
        paris_tz = pytz.timezone('Europe/Paris')
        current_time = datetime.now(paris_tz)
        timestamp = current_time.strftime('%y%m%d%H%M%S')
        filename = f'factures_auto_{timestamp}.xlsx'

        # Créer le fichier Excel avec formatage
        with pd.ExcelWriter(filename, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Factures', index=False)
            format_excel(writer, df)

        print(f"Fichier Excel créé : {filename}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Erreur lors de l'exécution: {str(e)}")

if __name__ == "__main__":
    main()
