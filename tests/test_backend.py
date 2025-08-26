import pickle
import src.utils.streamlit_utils as su


def test_df_cols():
    SAVE_FILE = "data/processed/401_cards.p"
    cards_df = pickle.load(open(SAVE_FILE, "rb"))
    assert "worldcat_matches" in cards_df.columns