import re
import streamlit as st
import pandas as pd
import requests
import json

# todo
# texte informatif
# cas d'usages
# not responsive grille
# recherche mot-clés complexe (plusieurs mots)
# conservation des logs utilisateur.ice.s.

# done
# réponse sous forme de liste et pas grille de micro-concept 
# division des mots avec virgules
# recherche par valeur et par case
# fix bug : recherche précédente reste
# fuzzy matching sur substring aussi avec sélection de micro-concept




# --- Paramètres ---
param = {'ontologie': "src/ontologie2.csv"}

st.set_page_config(layout='wide',
    initial_sidebar_state="expanded",
    page_title="IEML",
)
st.title("Navigation de l'ontologie de la littérature en IEML et recherche d'articles")

# --- Grille / maps ---
position_map = {
    "quand ?": "a1", "quoi ?": "a2", "où ?": 'a3',
    "qui ?": "b1", "thème": "b2", "à qui ?": "b3",
    "pourquoi ?": "c1", "par quoi ?": "c2", "comment ?": "c3"
}

layout = [['a1', 'a2', 'a3'], ['b1', 'b2', 'b3'], ['c1', 'c2', 'c3']]

reverse_map = {
"a1":"quand",
"a2":"quoi",
"a3":"ou",
"b1":"qui",
"b2":"theme",
"b3":"a_qui",
"c1":"pourquoi",
"c2":"par_quoi",
"c3":"comment"
}

label_map = {"quand":"quand ?",
"quoi":"quoi ?",
"ou":"où ?",
"qui":"qui ?",
"theme":"thème",
"a_qui":"à qui ?",
"pourquoi":"pourquoi ?",
"par_quoi":"par quoi ?",
"comment":"comment ?"
}

# --- Chargement des données ---
@st.cache_data
def load_data(path):
    return pd.read_csv(path)

data = load_data(param['ontologie'])

# --- Helpers / init ---
if "selected_cells" not in st.session_state:
    # set of normalized strings (no field info)
    st.session_state.selected_cells = set()

if "keyword" not in st.session_state:
    st.session_state.keyword = ""

if "afficher_resultats" not in st.session_state:
    st.session_state["afficher_resultats"] = False

if "show_isidore_results" not in st.session_state:
    st.session_state["show_isidore_results"] = False

def normalize_val(v):
    if v is None:
        return ""
    return str(v).strip()

import hashlib

def make_unique_key(prefix, s, index=None):
    """
    Génère un key unique pour Streamlit.
    - prefix : type de bouton (ex. "mc", "result", "index")
    - s : valeur du bouton
    - index : optionnel, index de la ligne ou autre identifiant unique
    """
    base = s if index is None else f"{s}_{index}"
    # hachage pour éviter caractères spéciaux
    hash_str = hashlib.md5(base.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{hash_str}"

# --- Fonctions UI / logique ---

def get_active_keyword():
    """Détermine le mot-clé actif, soit depuis l'input utilisateur, soit depuis une sélection"""
    if "keyword" not in st.session_state:
        st.session_state.keyword = ""

    # cas : clic sur un mot-clé de la sidebar
    if "new_keyword" in st.session_state:
        st.session_state.keyword = st.session_state.new_keyword
        del st.session_state.new_keyword
        st.session_state.selected_cells.clear()
        st.session_state["show_isidore_results"] = False  # reset
        st.session_state["afficher_resultats"] = False    # reset aussi ici
        st.rerun()

    # input utilisateur
    keyword_input = st.text_input("Entrez un mot-clé (ex. pouvoir)", st.session_state.keyword)
    if keyword_input != st.session_state.keyword:
        st.session_state.keyword = keyword_input
        st.session_state.selected_cells.clear()
        st.session_state["show_isidore_results"] = False
        st.session_state["afficher_resultats"] = False    # reset aussi ici
        st.rerun()

    return st.session_state.keyword


def display_board(entry):
    st.markdown(f"## Mot-clé : `{entry['mot']}`")
    for row in layout:
        cols = st.columns(3, vertical_alignment='center')
        for i, pos in enumerate(row):
            field = reverse_map.get(pos, "?")
            raw_value = entry.get(field, "")
            if isinstance(raw_value, float) and pd.isna(raw_value):
                raw_value = ""
            val_clean = normalize_val(raw_value)

            # For consistency we store only values (strings) in session_state.selected_cells
            selected = val_clean and (val_clean in st.session_state.selected_cells)
            bg_color = "#EF9A9A" if selected else "#f9f9f9"

            with cols[i]:
                st.markdown(
                    f"""
                    <div style="background-color: {bg_color}; padding: 6px; border-radius: 6px; text-align: center; border: 1px solid #ccc;">
                        <span style='font-size:14px;font-family:monospace;font:bold'>{val_clean if val_clean else '–'}</span><br>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # If the cell is empty, don't allow selecting it (we no longer keep field info)
                if not val_clean:
                    st.button(label_map[field] + " (vide)", key=f"{entry['mot']}_{pos}_disabled", disabled=True, use_container_width=True)
                else:
                    key_btn = make_unique_key("cell", f"{entry['mot']}_{val_clean}", pos)
                    if st.button(label_map[field], key=key_btn, use_container_width=True):
                        if val_clean in st.session_state.selected_cells:
                            st.session_state.selected_cells.remove(val_clean)
                        else:
                            st.session_state.selected_cells.add(val_clean)
                        st.rerun()


def display_microconcept_list(selected_values):
    """
    Affiche :
    1️⃣ La liste des micro-concepts liés à la sélection courante (inclut * et ~)
    2️⃣ La liste des mots-clés contenant ces micro-concepts
    """

    st.markdown("## Micro-concepts liés à la sélection")

    # Normaliser la sélection (garder uniquement les valeurs non vides)
    filters = [str(v).strip() for v in selected_values if v and str(v).strip()]
    
    # Si aucune sélection, on n'affiche rien
    if not filters:
        st.info("Sélectionnez un micro-concept pour afficher les résultats.")
        return

    # --- Récupérer toutes les lignes correspondant à la sélection ---
    match_func = make_selection_match_function(filters)
    matching_rows = data[data.apply(match_func, axis=1)]

    if matching_rows.empty:
        st.info("Aucune correspondance pour cette sélection.")
        return

    # --- Extraire tous les micro-concepts présents dans ces lignes ---
    micro_concepts = []
    for field in reverse_map.values():
        for cell in matching_rows[field].dropna():
            tokens = _tokenize_cell(str(cell), keep_special=True)  # inclut * et ~
            micro_concepts.extend(tokens)

    micro_concepts = sorted(set(micro_concepts))

    # Affichage liste micro-concepts
    if micro_concepts:
        st.markdown("### Micro-concepts disponibles")
        for val in micro_concepts:
            selected = val in st.session_state.selected_cells
            label = f"✅ {val}" if selected else val
            key_btn = make_unique_key("mc", val)
            if st.button(label, key=key_btn):
                if val in st.session_state.selected_cells:
                    st.session_state.selected_cells.remove(val)
                else:
                    st.session_state.selected_cells.add(val)
                st.session_state["afficher_resultats"] = False
                st.rerun()

    else:
        st.caption("Aucun micro-concept valide trouvé.")

    # --- Afficher les mots-clés associés aux micro-concepts sélectionnés ---
    st.markdown("## Mots-clés avec micro-concepts sélectionnés")

    # Matching substring sur tous les tokens
    match_func = make_selection_match_function(filters)
    associated_keywords = data[data.apply(match_func, axis=1)]["mot"].dropna().unique()
    associated_keywords = sorted([kw for kw in associated_keywords if kw.lower() != st.session_state.keyword.lower()])

    if associated_keywords:
        for kw in associated_keywords:
            key_btn = make_unique_key("result", kw)
            if st.button(kw, key=key_btn):
                st.session_state["new_keyword"] = kw
                st.session_state.selected_cells.clear()
                st.session_state["afficher_resultats"] = False
                st.rerun()

    else:
        st.info("Aucun mot-clé associé trouvé pour cette sélection.")

def make_match_function(term):
    term = str(term).lower().strip()
    if not term:
        return lambda row: False

    def match(row):
        # exclude exact same mot (optional depending on behavior)
        try:
            first = str(row.iloc[0]).strip().lower()
        except Exception:
            first = ""
        if first == term:
            return False
        return any(term in str(cell).lower() for cell in row.values if pd.notnull(cell))
    return match


def normalize_val(val):
    """Supprime espaces superflus et casse"""
    if pd.isnull(val):
        return ""
    return str(val).strip()

def _tokenize_cell(cell_str, keep_special=True):
    """
    Découpe une cellule en tokens.
    - Sépare par , | /
    - Supprime espaces superflus
    - keep_special=True → conserve * et ~
    """
    if pd.isnull(cell_str):
        return []
    cell_str = str(cell_str).strip().lower()
    tokens = re.split(r'[,\|/]+', cell_str)
    tokens = [t.strip() for t in tokens if t.strip()]
    if not keep_special:
        tokens = [t for t in tokens if not t.startswith(("*", "~"))]
    return tokens

    
def make_selection_match_function(filters, debug=False):
    """
    Match une ligne uniquement si chaque filtre est trouvé dans au moins une cellule.
    - Ignore les cellules vides
    - Utilise substring matching
    - Inclut les tokens avec * et ~ pour le match
    """
    if not filters:
        # Aucun filtre → ne rien matcher
        return lambda row: False

    norm_filters = [str(f).strip().lower() for f in filters if f.strip()]

    def match(row):
        for f in norm_filters:
            found = False
            for cell in row.values:
                if pd.isnull(cell):
                    continue
                tokens = _tokenize_cell(str(cell), keep_special=True)
                for t in tokens:
                    if f in t or t in f:
                        found = True
                        if debug:
                            print(f"DEBUG MATCH: filtre='{f}' trouve dans token='{t}' pour mot='{row['mot']}'")
                        break
                if found:
                    break
            if not found:
                # if debug:
                #     print(f"DEBUG NO MATCH: filtre='{f}' non trouvé pour mot='{row['mot']}', tokens={tokens}")
                return False
        return True

    return match

def display_entry_and_matches(entry):
    display_board(entry)
    with col2:
        st.markdown("# Articles ")
        if st.button("Rechercher des articles dans Isidore", key=f"search_isidore_{entry['mot']}"):
            st.session_state["show_isidore_results"] = True


@st.cache_data(show_spinner=False)
def get_isidore_articles(query):
    url = f'https://api.isidore.science/resource/search?q={query}&replies=100&output=json'
    res = requests.get(url)
    content = json.loads(res.text)
    articles = [reply['isidore'] for reply in content['response']['replies']['content']['reply']]
    return articles

# --- Layout ---
col1, col2 = st.columns([1, 1], vertical_alignment='top')

# sidebar index
with st.sidebar:
    st.markdown("### Mots-clés définis")
    mots = sorted(data["mot"].dropna().unique(), key=str.casefold)
    for mot in mots:
        key_btn = make_unique_key("index", mot)
        if st.button(mot, key=key_btn):
            st.session_state["new_keyword"] = mot
            st.session_state.selected_cells.clear()
            st.rerun()


with col1:
    st.title("IEML")

    keyword = get_active_keyword()
    entry = data[data["mot"].str.lower() == keyword.lower()].squeeze() if keyword else None

    if entry is not None and not entry.empty:
        display_entry_and_matches(entry)

    elif keyword:
        related_entries = data[data.apply(make_match_function(keyword), axis=1)]
        if not related_entries.empty:
            st.info("Ce mot-clé n'est pas dans l'ontologie mais correspond à un micro-concept IEML")
            st.markdown(f"### Mots-clés contenant le micro-concept `{keyword}`")
            for _, row in related_entries.iterrows():
                key_btn = make_unique_key("related", row["mot"], index=row.name)
                if st.button(row["mot"], key=key_btn):
                    st.session_state["new_keyword"] = row["mot"]
                    st.session_state.selected_cells.clear()
                    st.rerun()


    # Bouton Recherche
    if st.button("Recherche", icon='🔍'):
        filters = [normalize_val(v) for v in st.session_state.selected_cells]
        if not filters:
            st.error("Sélectionnez au moins une cellule.")
        else:
            has_non_empty = any(f.strip() for f in filters)
            if not has_non_empty:
                st.error("Sélectionnez au moins une cellule avec une valeur non vide.")
            else:
                st.session_state["afficher_resultats"] = True

    # Affichage résultats
    if st.session_state.get("afficher_resultats", False):
        filters = list(st.session_state.selected_cells)
        # DEBUG: affiche la sélection actuelle
        st.caption(f"DEBUG — selected_cells: {sorted(list(st.session_state.selected_cells))}")
        display_microconcept_list(filters)

        match_func = make_selection_match_function(filters)
        matches = data[data.apply(match_func, axis=1)]

with col2:
    if st.session_state.get("show_isidore_results") and keyword:
        articles = get_isidore_articles(keyword)
        if not articles:
            st.info("Aucun article trouvé.")
        else:
            titles = [a['title'][0]['$'] for a in articles]
            urls = [a['url'] for a in articles]
            data_df = pd.DataFrame({'title': titles, 'url': urls})
            st.table(data_df)


# Debug

# filters = ['pays']
# match_func = make_selection_match_function(filters, debug=True)
# for _, row in data.iterrows():
#     if match_func(row):
#         print(f"Match trouvé pour mot : {row['mot']}")
