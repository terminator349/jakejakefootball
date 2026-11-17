"""The draft class: real NFL player names and real Madden NFL 26 overall
ratings (0-99 scale, same convention the rest of this project uses),
pulled from playerratingspro.com's Madden 26 position pages in November
2026. Ordered best-to-worst exactly as that site ranks each position.

The one exception is long snapper: Madden doesn't publish LS ratings on
that site, so those eight are my own rough estimate (clearly lower-signal
than everything else here, but LS barely affects the draft - one spot per
team, no real differentiation in what the position needs).

Six teams drafting 53 rounds need real depth at every position (see
draft/roster_rules.ROSTER_TEMPLATE for the per-team targets), which is why
even deep bench and special-teams names are included, not just starters.
"""

from dataclasses import dataclass, field

# (name, Madden 26 overall), best to worst, as rated on playerratingspro.com.
POSITION_PLAYERS = {
    "QB": [
        ("Josh Allen", 99), ("Lamar Jackson", 99), ("Joe Burrow", 97), ("Patrick Mahomes", 95),
        ("Matthew Stafford", 88), ("Jared Goff", 87), ("Jalen Hurts", 86), ("Justin Herbert", 86),
        ("Baker Mayfield", 85), ("Jayden Daniels", 85), ("Brock Purdy", 84), ("Dak Prescott", 84),
        ("Jordan Love", 83), ("Tua Tagovailoa", 82), ("C.J. Stroud", 81), ("Geno Smith", 80),
        ("Bo Nix", 79), ("Kyler Murray", 79), ("Drake Maye", 78), ("Sam Darnold", 77),
        ("Aaron Rodgers", 76), ("Russell Wilson", 76), ("Bryce Young", 75), ("Caleb Williams", 75),
        ("Trevor Lawrence", 75), ("Justin Fields", 74), ("Michael Penix Jr.", 74), ("J.J. McCarthy", 73),
    ],
    "RB": [
        ("Saquon Barkley", 99), ("Derrick Henry", 98), ("Jahmyr Gibbs", 95), ("Christian McCaffrey", 94),
        ("Bijan Robinson", 92), ("Joe Mixon", 91), ("Josh Jacobs", 90), ("James Cook III", 89),
        ("Jonathan Taylor", 88), ("Kenneth Walker III", 88), ("Bucky Irving", 87), ("Nick Chubb", 87),
        ("Kyren Williams", 86), ("Tony Pollard", 86), ("Aaron Jones Sr.", 85), ("Chuba Hubbard", 85),
        ("James Conner", 85), ("Alvin Kamara", 84), ("Breece Hall", 84), ("David Montgomery", 84),
        ("Ashton Jeanty", 83), ("De'Von Achane", 83), ("Isiah Pacheco", 83), ("J.K. Dobbins", 82),
        ("Najee Harris", 82), ("Travis Etienne Jr.", 82), ("Brian Robinson Jr.", 81), ("Chase Brown", 81),
        ("D'Andre Swift", 81), ("Tyler Allgeier", 81),
    ],
    "WR": [
        ("Ja'Marr Chase", 99), ("Justin Jefferson", 99), ("Amon-Ra St. Brown", 96), ("CeeDee Lamb", 95),
        ("Tyreek Hill", 95), ("Terry McLaurin", 94), ("A.J. Brown", 93), ("Mike Evans", 93),
        ("Drake London", 91), ("Davante Adams", 90), ("DeVonta Smith", 89), ("Nico Collins", 89),
        ("Puka Nacua", 88), ("Stefon Diggs", 88), ("Brandon Aiyuk", 87), ("Malik Nabers", 87),
        ("Tee Higgins", 87), ("Chris Olave", 86), ("Cooper Kupp", 86), ("DJ Moore", 86),
        ("Garrett Wilson", 86), ("Jaxon Smith-Njigba", 86), ("Chris Godwin Jr.", 85), ("Courtland Sutton", 85),
        ("DK Metcalf", 85), ("Jaylen Waddle", 85), ("Zay Flowers", 85), ("Brian Thomas Jr.", 84),
        ("Jerry Jeudy", 84), ("Jordan Addison", 84), ("Ladd McConkey", 84), ("Deebo Samuel Sr.", 83),
        ("George Pickens", 83), ("Jakobi Meyers", 83), ("Rashee Rice", 83), ("DeAndre Hopkins", 82),
        ("Jameson Williams", 82), ("Khalil Shakir", 82), ("Michael Pittman Jr.", 82), ("Tank Dell", 82),
        ("Calvin Ridley", 81), ("Christian Kirk", 81), ("Darnell Mooney", 81), ("Jayden Reed", 81),
        ("Rashod Bateman", 81), ("Adam Thielen", 80), ("Jauan Jennings", 80), ("Josh Downs", 80),
        ("Marquise Brown", 80), ("Xavier Worthy", 80),
    ],
    "TE": [
        ("George Kittle", 98), ("Travis Kelce", 93), ("Trey McBride", 92), ("Mark Andrews", 91),
        ("Brock Bowers", 90), ("David Njoku", 89), ("T.J. Hockenson", 88), ("Dallas Goedert", 87),
        ("Sam LaPorta", 86), ("Evan Engram", 85), ("Pat Freiermuth", 84), ("Hunter Henry", 83),
        ("Cole Kmet", 82), ("Darren Waller", 82), ("Jake Ferguson", 81), ("Jonnu Smith", 81),
        ("Dalton Schultz", 80), ("Isaiah Likely", 80), ("Mike Gesicki", 79), ("Tucker Kraft", 79),
        ("Kyle Pitts Sr.", 78), ("Zach Ertz", 78),
    ],
    "OT": [
        ("Lane Johnson", 99), ("Trent Williams", 97), ("Jordan Mailata", 96), ("Penei Sewell", 96),
        ("Tristan Wirfs", 96), ("Laremy Tunsil", 94), ("Rashawn Slater", 93), ("Christian Darrisaw", 92),
        ("Dion Dawkins", 91), ("Ronnie Stanley", 90), ("Garett Bolles", 89), ("Andrew Thomas", 88),
        ("Kolton Miller", 87), ("Taylor Decker", 87), ("Zach Tom", 87), ("Brian O'Neill", 86),
        ("Jake Matthews", 86), ("Taylor Moton", 86), ("Bernhard Raimann", 85), ("Spencer Brown", 85),
        ("Trent Brown", 85), ("Paris Johnson Jr.", 84), ("Rob Havenstein", 84), ("Braden Smith", 83),
        ("Charles Cross", 83), ("Joe Alt", 82), ("Luke Goedeke", 82), ("Mike McGlinchey", 82),
    ],
    "OG": [
        ("Quinn Meinerz", 95), ("Chris Lindstrom", 94), ("Joe Thuney", 93), ("Quenton Nelson", 92),
        ("Kevin Zeitler", 91), ("Trey Smith", 90), ("Landon Dickerson", 88), ("Tyler Smith", 88),
        ("Sam Cosmi", 87), ("Joel Bitonio", 85), ("Kevin Dotson", 85), ("Alijah Vera-Tucker", 84),
        ("Damien Lewis", 83), ("Dominick Puni", 83), ("John Simpson", 82), ("Mike Onwenu", 82),
        ("Robert Hunt", 82), ("Mekhi Becton Sr.", 81), ("Isaac Seumalo", 80), ("Teven Jenkins", 80),
        ("Will Fries", 80), ("Cesar Ruiz", 79),
    ],
    "C": [
        ("Creed Humphrey", 94), ("Erik McCoy", 89), ("Tyler Linderbaum", 88), ("Elgton Jenkins", 87),
        ("Zach Frazier", 84), ("Ryan Kelly", 83), ("Tyler Biadasz", 81), ("Hjalte Froholdt", 80),
        ("Drew Dalman", 79), ("Joe Tippmann", 79), ("Connor McGovern", 78), ("Ted Karras", 78),
        ("Aaron Brewer", 77), ("Jackson Powers-Johnson", 77), ("Cam Jurgens", 76),
    ],
    "EDGE": [
        ("Myles Garrett", 99), ("Micah Parsons", 98), ("Maxx Crosby", 96), ("T.J. Watt", 96),
        ("Nick Bosa", 95), ("Aidan Hutchinson", 93), ("Trey Hendrickson", 92), ("Danielle Hunter", 91),
        ("Josh Hines-Allen", 90), ("Will Anderson Jr.", 89), ("Alex Highsmith", 88), ("Greg Rousseau", 88),
        ("DeMarcus Lawrence", 87), ("Khalil Mack", 87), ("Brian Burns", 86), ("Jared Verse", 86),
        ("Joey Bosa", 85), ("Josh Sweat", 85), ("George Karlaftis", 84), ("Nik Bonitto", 84),
        ("Andrew Van Ginkel", 83), ("Jonathan Greenard", 83), ("Von Miller", 83), ("Jaelan Phillips", 82),
        ("Odafe Oweh", 82), ("Rashan Gary", 82), ("Abdul Carter", 81), ("Montez Sweat", 81),
    ],
    "DT": [
        ("Chris Jones", 97), ("Dexter Lawrence II", 97), ("Derrick Brown", 95), ("Cam Heyward", 94),
        ("Nnamdi Madubuike", 93), ("Vita Vea", 93), ("Jeffery Simmons", 92), ("Quinnen Williams", 91),
        ("Jalen Carter", 90), ("DeForest Buckner", 88), ("Jonathan Allen", 88), ("Leonard Williams", 87),
        ("Zach Allen", 86), ("D.J. Reader", 85), ("Grover Stewart", 85), ("Kobie Turner", 85),
        ("Milton Williams", 85), ("Zach Sieler", 84), ("Alim McNeill", 83), ("Daron Payne", 83),
        ("Kenny Clark", 83), ("Braden Fiske", 82), ("Calais Campbell", 82), ("Grady Jarrett", 82),
        ("Ed Oliver", 81), ("Javon Hargrave", 81), ("Christian Barmore", 80),
    ],
    "LB": [
        ("Fred Warner", 97), ("Roquan Smith", 94), ("Bobby Wagner", 91), ("Demario Davis", 90),
        ("Lavonte David", 88), ("Zack Baun", 88), ("Foyesade Oluokun", 87), ("Bobby Okereke", 86),
        ("Dre Greenlaw", 86), ("Devin Lloyd", 85), ("Drue Tranquill", 84), ("Jack Campbell", 84),
        ("Leo Chenal", 84), ("Matt Milano", 84), ("Blake Cashman", 83), ("Daiyan Henley", 83),
        ("Jeremiah Owusu-Koramoah", 83), ("Nick Bolton", 83), ("Kaden Elliss", 82), ("Logan Wilson", 82),
        ("Patrick Queen", 82), ("Quincy Williams", 82), ("Robert Spillane", 82), ("Shaq Thompson", 81),
        ("T.J. Edwards", 81), ("Azeez Al-Shaair", 80), ("Ernest Jones IV", 80), ("Frankie Luvu", 80),
        ("Jordyn Brooks", 80), ("Tremaine Edmunds", 80), ("Zaire Franklin", 80), ("Alex Anzalone", 79),
        ("Cody Barton", 79), ("Edgerrin Cooper", 79), ("Germaine Pratt", 79), ("Quay Walker", 79),
        ("Terrel Bernard", 79), ("Cole Holcomb", 78), ("Ivan Pace Jr.", 78), ("Mack Wilson Sr.", 78),
        ("Pete Werner", 78), ("Trenton Simpson", 78), ("Alex Singleton", 77),
    ],
    "CB": [
        ("Patrick Surtain II", 97), ("Christian Gonzalez", 95), ("Jalen Ramsey", 94), ("Sauce Gardner", 94),
        ("Trent McDuffie", 94), ("Derek Stingley Jr.", 93), ("Marlon Humphrey", 92), ("Jaire Alexander", 91),
        ("Denzel Ward", 90), ("Jaylon Johnson", 89), ("A.J. Terrell Jr.", 88), ("Devon Witherspoon", 88),
        ("Kenny Moore II", 88), ("Charvarius Ward Sr.", 87), ("DaRon Bland", 87), ("Jamel Dean", 86),
        ("Jaycee Horn", 86), ("Marshon Lattimore", 86), ("Riq Woolen", 86), ("Byron Murphy Jr.", 85),
        ("Carlton Davis III", 85), ("Christian Benford", 85), ("Quinyon Mitchell", 85), ("Darius Slay Jr.", 84),
        ("L'Jarius Sneed", 84), ("Taron Johnson", 84), ("Travis Hunter", 84), ("Trevon Diggs", 84),
        ("Chidobe Awuzie", 83), ("Cooper DeJean", 83), ("D.J. Reed", 83), ("Deommodore Lenoir", 82),
        ("Kyler Gordon", 82), ("Paulson Adebo", 82), ("Cam Taylor-Britt", 81), ("Greg Newsome II", 81),
        ("Kamari Lassiter", 81), ("Nate Hobbs", 81), ("Darious Williams", 80), ("Garrett Williams", 80),
    ],
    "S": [
        ("Jessie Bates III", 95), ("Derwin James Jr.", 93), ("Xavier McKinney", 93), ("Budda Baker", 92),
        ("Minkah Fitzpatrick", 92), ("Antoine Winfield Jr.", 91), ("Kerby Joseph", 90), ("Kyle Hamilton", 90),
        ("Brian Branch", 89), ("Harrison Smith", 88), ("Justin Reid", 87), ("Jabrill Peppers", 86),
        ("Julian Love", 86), ("C.J. Gardner-Johnson", 84), ("Talanoa Hufanga", 84), ("Brandon Jones", 83),
        ("Jalen Pitre", 83), ("Jaquan Brisker", 83), ("Jeremy Chinn", 83), ("Jevon Holland", 83),
        ("Jimmie Ward", 83), ("Camryn Bynum", 82), ("DeShon Elliott", 82), ("Josh Metellus", 82),
        ("Tre'von Moehrig", 82), ("Grant Delpit", 81), ("Jalen Thompson", 81), ("Kevin Byard III", 81),
    ],
    "K": [
        ("Brandon Aubrey", 87), ("Chris Boswell", 85), ("Harrison Butker", 82), ("Ka'imi Fairbairn", 80),
        ("Cameron Dicker", 79), ("Chase McLaughlin", 79), ("Jason Myers", 79), ("Nick Folk", 79),
    ],
    "P": [
        ("AJ Cole", 85), ("Logan Cooke", 83), ("Michael Dickson", 83), ("Corey Bojorquez", 82),
        ("Bradley Pinion", 81), ("Bryan Anger", 81), ("JK Scott", 80), ("Bryce Baringer", 79),
    ],
    # No LS ratings are published on the Madden 26 ratings site used for the rest of this
    # file; these eight are my own rough estimate, not a real-world source.
    "LS": [
        ("Morgan Cox", 75), ("Thomas Hennessy", 72), ("Tyler Ott", 71), ("Rick Lovato", 66),
        ("Jon Weeks", 65), ("Beau Brinkley", 61), ("Zach Wood", 58), ("Christian Kuntz", 56),
    ],
}


@dataclass
class Player:
    id: str
    name: str
    position: str
    overall: int
    team_id: str | None = field(default=None)
    salary: float | None = field(default=None)
    pick_number: int | None = field(default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "position": self.position,
            "overall": self.overall,
            "team_id": self.team_id,
            "salary": self.salary,
            "pick_number": self.pick_number,
        }


def build_player_pool() -> list[Player]:
    """Build the full draft class from POSITION_PLAYERS. Deterministic (no
    randomness involved), so the draft class is identical every run."""
    pool: list[Player] = []
    for position, players in POSITION_PLAYERS.items():
        for index, (name, overall) in enumerate(players):
            pool.append(Player(
                id=f"{position}-{index + 1:02d}",
                name=name,
                position=position,
                overall=overall,
            ))
    return pool


if __name__ == "__main__":
    players = build_player_pool()
    counts = {}
    for p in players:
        counts[p.position] = counts.get(p.position, 0) + 1
    print(f"Total players: {len(players)}")
    for position, count in counts.items():
        print(f"  {position}: {count}")
