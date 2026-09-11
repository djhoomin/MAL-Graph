"""Cypher used by the API, in one place."""

REL_TYPES = ["LISTED", "HAS_CHARACTER", "VOICES", "WORKED_ON", "RELATED_TO", "PRODUCED_BY", "HAS_GENRE"]
NODE_LABELS = ["Anime", "Character", "Person", "Studio", "Genre", "User"]

SEARCH = {
    "Anime": """
        MATCH (n:Anime)
        WHERE toLower(n.title) CONTAINS $q OR toLower(coalesce(n.title_english, '')) CONTAINS $q
        RETURN n ORDER BY n.watched DESC, n.members DESC LIMIT $limit
    """,
    "Character": """
        MATCH (n:Character) WHERE toLower(n.name) CONTAINS $q
        RETURN n ORDER BY n.favorites DESC LIMIT $limit
    """,
    "Person": """
        MATCH (n:Person) WHERE toLower(n.name) CONTAINS $q
        RETURN n ORDER BY n.favorites DESC LIMIT $limit
    """,
    "Studio": "MATCH (n:Studio) WHERE toLower(n.name) CONTAINS $q RETURN n LIMIT $limit",
    "Genre": "MATCH (n:Genre) WHERE toLower(n.name) CONTAINS $q RETURN n LIMIT $limit",
}

NODE = "MATCH (n:%s {mal_id: $id}) RETURN n"
NODE_USER = "MATCH (n:User {username: $id}) RETURN n"

DEGREES = """
    MATCH (n:%s {mal_id: $id})-[r]-(m)
    RETURN type(r) AS type, labels(m)[0] AS label, count(*) AS n
"""

# Neighbours; `rels` = allowed relationship types, `only_watched` drops non-watched Anime.
NEIGHBORS = """
    MATCH (n:%s {mal_id: $id})-[r]-(m)
    WHERE type(r) IN $rels
      AND (NOT $only_watched OR NOT m:Anime OR coalesce(m.watched, false))
      AND ($lang IS NULL OR type(r) <> 'VOICES' OR r.language = $lang)
    RETURN n, r, m LIMIT $limit
"""
NEIGHBORS_USER = """
    MATCH (n:User {username: $id})-[r:LISTED]->(m)
    WHERE (NOT $only_watched OR coalesce(m.watched, false))
    RETURN n, r, m LIMIT $limit
"""

# Memgraph BFS shortest path. Filter lambda excludes labels and, optionally, non-watched anime.
SHORTEST_PATH = """
    MATCH (a:%s {mal_id: $from_id}), (b:%s {mal_id: $to_id})
    MATCH p = (a)-[*BFS ..%d (r, n |
        NOT labels(n)[0] IN $exclude
        AND (NOT $only_watched OR NOT n:Anime OR coalesce(n.watched, false))
        AND ($lang IS NULL OR type(r) <> 'VOICES' OR r.language = $lang)
    )]-(b)
    RETURN p
"""
ALL_SHORTEST_PATHS = """
    MATCH (a:%s {mal_id: $from_id}), (b:%s {mal_id: $to_id})
    MATCH p = (a)-[*ALLSHORTEST ..%d (r, n | 1) w (r, n |
        NOT labels(n)[0] IN $exclude
        AND (NOT $only_watched OR NOT n:Anime OR coalesce(n.watched, false))
        AND ($lang IS NULL OR type(r) <> 'VOICES' OR r.language = $lang)
    )]-(b)
    RETURN p LIMIT $limit
"""

# Voice actor → characters → anime they appear in.
VA_ROLES = """
    MATCH (p:Person {mal_id: $id})-[v:VOICES]->(c:Character)<-[h:HAS_CHARACTER]-(a:Anime)
    WHERE (NOT $only_watched OR coalesce(a.watched, false))
      AND ($lang IS NULL OR v.language = $lang)
    RETURN p, v, c, h, a
    ORDER BY a.watched DESC, a.members DESC
"""

USER_SUMMARY = """
    MATCH (u:User)-[l:LISTED]->(a:Anime)
    RETURN u.username AS username, l.status AS status, count(*) AS n,
           sum(CASE WHEN a.fetched_at IS NULL THEN 1 ELSE 0 END) AS unfetched
    ORDER BY status
"""
