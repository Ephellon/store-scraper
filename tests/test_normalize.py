from catalog.normalize import clean_title, strip_edition_noise


def test_clean_title_splits_camel_case_tokens():
    assert clean_title("DarkQuestRemastered") == "Dark Quest Remastered"
    assert clean_title("Damagex2DragonSpira") == "Damagex 2 Dragon Spira"


def test_strip_edition_noise_after_token_boundary_split():
    assert strip_edition_noise("DarkQuestRemastered") == "Dark Quest"
    assert strip_edition_noise("SuperGame2DeluxeEdition") == "Super Game 2"
