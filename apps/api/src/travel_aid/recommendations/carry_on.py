"""Airlines whose lowest economy fare charges for a full-size carry-on bag.

Search results do not report fare types or baggage, so Mid-range excludes these carriers and
labels every other pick "carry-on likely included". Fare-type rules on other airlines (for
example United basic economy on US domestic routes) cannot be detected from results.
Review this list when airline bag policies change.
"""

CARRY_ON_FEE_AIRLINES = frozenset(
    {
        "NK",  # Spirit Airlines
        "F9",  # Frontier Airlines
        "G4",  # Allegiant Air
        "SY",  # Sun Country Airlines
        "MX",  # Breeze Airways
        "F8",  # Flair Airlines
        "Y4",  # Volaris
        "VB",  # Viva Aerobus
        "JA",  # JetSMART
        "FR",  # Ryanair
        "RK",  # Ryanair UK
        "W6",  # Wizz Air
        "W4",  # Wizz Air Malta
        "W9",  # Wizz Air UK
        "U2",  # easyJet
        "EC",  # easyJet Europe
        "VY",  # Vueling
        "HV",  # Transavia
        "TO",  # Transavia France
        "N0",  # Norse Atlantic Airways
        "OG",  # PLAY
    }
)
