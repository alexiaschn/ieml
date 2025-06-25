import streamlit as st
import pandas as pd


# nettoyer corpus
# système flexionnel avec recherche floue sur les signes particuliers * ~ etc.
# connexion avec un corpus 'input/erudit_articles.csv'


# --- Paramètres ---

param = {'ontologie': "src/ontologie.csv", 
        'corpus': 'src/test_corpus.csv'}

st.set_page_config(layout='wide')

# --- Configuration de la grille ---



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
corpus = load_data(param['corpus'])


# --- Fonctions ---

def get_active_keyword():
    """Détermine le mot-clé actif, soit depuis l'input utilisateur, soit depuis une sélection"""
    if "keyword" not in st.session_state:
        st.session_state.keyword = ""

    if "new_keyword" in st.session_state:
        st.write(st.session_state['new_keyword'])
        # On vient de cliquer sur un mot — mise à jour du keyword
        st.session_state.keyword = st.session_state.new_keyword
        del st.session_state.new_keyword
        st.session_state.selected_cells.clear()
        st.rerun()

    return st.text_input("Entrez un mot-clé (ex. pouvoir)", st.session_state.keyword)


def display_board(entry):
    st.markdown(f"## Mot : {entry['mot']}")
    for row in layout:
        cols = st.columns(3, vertical_alignment='center')
        for i, pos in enumerate(row):
            field = reverse_map.get(pos, "?")
            value = entry.get(field, "")
            if type(value) == float:
                value = ''
            label = value
            key = f"{entry['mot']}_{pos}"
            selected = (field, value) in st.session_state.selected_cells
            bg_color = "#EF9A9A" if selected else "#f9f9f9"

            with cols[i]:
                st.markdown(
                    f"""
                    <div style="background-color: {bg_color}; padding: 6px; border-radius: 6px; text-align: center; border: 1px solid #ccc;">
                        <span style='font-size:14px;font-family:monospace;font:bold'>{label}</span><br>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                if st.button(label_map[field], key=key, use_container_width=True):
                    if selected:
                        st.session_state.selected_cells.remove((field, value))
                    else:
                        st.session_state.selected_cells.add((field, value))
                    st.rerun()

def make_match_function(term):
    term = str(term).lower().strip()
    if not term:
        return lambda row: False  # Ne match rien si terme vide

    def match(row):   
        return (
            row.iloc[0] != term and
             any(
            term in str(cell).lower() for cell in row.values if pd.notnull(cell))
        )
    return match

def make_selection_match_function(filters):
    def match(row):
        for field, val in filters.items():
            cell_val = str(row.get(field, "")).strip()
            if val:  # user selected a value
                if cell_val != val:
                    return False
            else:  # user clicked an empty cell → we want any non-empty value
                if not cell_val or cell_val.lower() == 'nan':
                    return False
        return True
    return match


def display_entry_and_matches(entry):
    display_board(entry)  # affiche la grille
    with col2:
        match_corpus = corpus[corpus.apply(make_match_function(entry["mot"]), axis=1)]
        st.markdown("# Articles liés")
        if match_corpus.empty:
            st.info("Aucun article trouvé.")
        else:
            st.table(match_corpus[['titre', 'revue']])

# Affichage de l'échiquier sur moitié gauche/article lié à droite

col1, col2 = st.columns([1, 1], vertical_alignment='top')  
with col1:
    st.title("IEML")

    keyword = get_active_keyword()
    entry = data[data["mot"].str.lower() == keyword.lower()].squeeze() if keyword else None

    
    if "selected_cells" not in st.session_state:
        st.session_state.selected_cells = set()
    
    # st.write(st.session_state.selected_cells)
    if entry is not None and not entry.empty:
        display_entry_and_matches(entry)

    # Sinon, cherche un micro-concept associé
    elif keyword:
        related_entries = data[data.apply(make_match_function(keyword), axis=1)]

        if not related_entries.empty:
            st.info("Ce mot-clé n'est pas dans l'ontologie mais est un micro-concept IEML")
            st.markdown(f"### Mots associés au micro-concept {keyword}")
            for _, row in related_entries.iterrows():
                if st.button(row["mot"], key=f"related_{row['mot']}"):
                    st.session_state["new_keyword"] = row["mot"]
                    st.session_state.selected_cells.clear()
                    st.rerun()
        else:
            st.warning("Aucun concept ni article trouvé.")


    if st.button("Recherche", help='''Recherche un mot-clé dans l'ontologie IEML à partir des rôles grammaticaux''' ):
        filters = dict(st.session_state.selected_cells)
        # st.write(st.session_state.selected_cells)
        # st.write(filters)
        if not filters:
            st.error("Sélectionnez au moins une cellule.")
        else:
            has_non_empty = any(val.strip() for val in filters.values())

            if not has_non_empty:
                st.error("Sélectionnez au moins une cellule avec une valeur non vide.")
                st.rerun()
            else:
                st.session_state["afficher_resultats"] = True

    if st.session_state.get("afficher_resultats", False):
        filters = dict(st.session_state.selected_cells)
        match_func = make_selection_match_function(filters)
        matches = data[data.apply(match_func, axis=1)]
        if matches.empty or ((matches.iloc[0].get('mot', '') == keyword) and (matches.shape[0] == 1)) : 
            st.info("Aucun résultat. Cliquez sur le bouton ci-dessous pour réessayer.")
            if st.button("Nouvelle sélection"):
                st.session_state.selected_cells.clear()
                st.session_state["afficher_resultats"] = False
                st.rerun()
        else:
            st.markdown("## Mots filtrés")
            for _, row in matches.iterrows():
                if not row['mot'] == keyword:
                    if st.button(row["mot"], key=f"result_{row['mot']}"):
                        st.session_state["new_keyword"] = row["mot"]
                        st.session_state.selected_cells.clear()
                        st.session_state["afficher_resultats"] = False  # reset
                        st.rerun()



