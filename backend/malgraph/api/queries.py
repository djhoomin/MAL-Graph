"""Cypher used by the API, in one place."""

REL_TYPES = ["LISTED", "HAS_CHARACTER", "VOICES", "WORKED_ON", "RELATED_TO", "PRODUCED_BY", "HAS_GENRE"]
NODE_LABELS = ["Anime", "Character", "Person", "Studio", "Genre", "User"]

SEARCH = {
    "Anime": """
        MATCH (n:Anime)
        WHERE toLower(n.title) CONTAINS $q OR toLower(coalesce(n.title_english, '')) CONTAINS $q
        RETURN n ORDER BY coalesce(n.watched, false) DESC, coalesce(n.members, 0) DESC LIMIT $limit
    """,
    "Character": """
        MATCH (n:Character) WHERE toLower(n.name) CONTAINS $q
        RETURN n ORDER BY coalesce(n.favorites, 0) DESC LIMIT $limit
    """,
    "Person": """
        MATCH (n:Person) WHERE toLower(n.name) CONTAINS $q
        RETURN n ORDER BY coalesce(n.favorites, 0) DESC LIMIT $limit
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
        AND type(r) IN $rels
        AND (NOT $only_watched OR NOT n:Anime OR coalesce(n.watched, false))
        AND ($lang IS NULL OR type(r) <> 'VOICES' OR r.language = $lang)
    )]-(b)
    RETURN p
"""
ALL_SHORTEST_PATHS = """
    MATCH (a:%s {mal_id: $from_id}), (b:%s {mal_id: $to_id})
    MATCH p = (a)-[*ALLSHORTEST ..%d (r, n | 1) w (r, n |
        NOT labels(n)[0] IN $exclude
        AND type(r) IN $rels
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
    ORDER BY coalesce(a.watched, false) DESC, coalesce(a.members, 0) DESC
"""

USER_SUMMARY = """
    MATCH (u:User)-[l:LISTED]->(a:Anime)
    RETURN u.username AS username, l.status AS status, count(*) AS n,
           sum(CASE WHEN a.fetched_at IS NULL THEN 1 ELSE 0 END) AS unfetched
    ORDER BY status
"""

# Voice actors ranked by distinct characters in anime the user has watched (for the roster view).
ROSTER = """
    MATCH (p:Person)-[v:VOICES]->(c:Character)<-[h:HAS_CHARACTER]-(a:Anime)
    WHERE (NOT $only_watched OR coalesce(a.watched, false))
      AND (NOT $main_only OR h.role = 'Main')
      AND ($lang IS NULL OR v.language = $lang)
      AND ($q IS NULL OR toLower(p.name) CONTAINS $q)
    WITH p, count(DISTINCT c) AS characters, count(DISTINCT a) AS anime
    WHERE characters >= $min_characters
    RETURN p, characters, anime
    ORDER BY characters DESC, anime DESC, p.name
    LIMIT $limit
"""

# ---- insights -------------------------------------------------------------
INSIGHTS_LIST = """
    MATCH (u:User)-[l:LISTED]->(a:Anime)
    OPTIONAL MATCH (a)-[:PRODUCED_BY]->(s:Studio)
    WITH a, l, collect(DISTINCT {mal_id: s.mal_id, name: s.name}) AS studios
    OPTIONAL MATCH (a)-[:HAS_GENRE]->(g:Genre)
    RETURN a.mal_id AS mal_id, a.title AS title, a.title_english AS title_english, a.image_url AS image_url,
           a.type AS type, a.year AS year, a.season AS season, a.aired_from AS aired_from,
           a.episodes AS episodes, a.score AS score, a.members AS members,
           l.status AS status, l.score AS my_score, l.episodes_watched AS episodes_watched, l.updated_at AS updated_at,
           [s IN studios WHERE s.mal_id IS NOT NULL] AS studios,
           collect(DISTINCT {mal_id: g.mal_id, name: g.name, kind: g.kind}) AS genres
"""

# People ranked by how many listed anime they touch. kind = 'va' (VOICES via characters) or a staff position.
INSIGHTS_VA = """
    MATCH (u:User)-[l:LISTED]->(a:Anime)-[:HAS_CHARACTER]->(c:Character)<-[v:VOICES]-(p:Person)
    WHERE l.status IN $statuses AND ($lang IS NULL OR v.language = $lang)
    WITH p, collect(DISTINCT a.mal_id) AS anime_ids, count(DISTINCT c) AS characters,
         avg(CASE WHEN l.score > 0 THEN toFloat(l.score) END) AS avg_my_score
    WHERE size(anime_ids) >= $min
    RETURN p, anime_ids, characters, avg_my_score
    ORDER BY size(anime_ids) DESC, characters DESC, p.name LIMIT $limit
"""
INSIGHTS_STAFF = """
    MATCH (u:User)-[l:LISTED]->(a:Anime)<-[w:WORKED_ON]-(p:Person)
    WHERE l.status IN $statuses AND $position IN w.positions
    WITH p, collect(DISTINCT a.mal_id) AS anime_ids, 0 AS characters,
         avg(CASE WHEN l.score > 0 THEN toFloat(l.score) END) AS avg_my_score
    WHERE size(anime_ids) >= $min
    RETURN p, anime_ids, characters, avg_my_score
    ORDER BY size(anime_ids) DESC, p.name LIMIT $limit
"""

# Related anime (sequels etc.) of listed anime that are not on the list.
INSIGHTS_GAPS = """
    MATCH (u:User)-[l:LISTED]->(a:Anime)-[r:RELATED_TO]->(b:Anime)
    WHERE l.status IN $statuses AND r.relation IN $relations AND NOT (u)-[:LISTED]->(b)
    RETURN b.mal_id AS mal_id, b.title AS title, b.image_url AS image_url, b.score AS score, b.type AS type,
           b.year AS year, b.fetched_at IS NOT NULL AS fetched,
           collect({relation: r.relation, mal_id: a.mal_id, title: a.title, my_score: l.score, status: l.status}) AS via
    ORDER BY size(via) DESC, mal_id
"""

# ---- recommendations ------------------------------------------------------
# Unseen, fetched anime scored by the user's people. A person's weight = number of watched anime in which they
# have a MAIN role (VAs) / a key position (staff), scaled by the user's average score for that work. Only the
# user's top people count, and only main roles on the candidate side, so giant casts don't win by volume.
# Candidates in the same franchise as anything on the list are excluded via the precomputed Anime.seen_franchise flag
# (ingest.mark_seen_franchise, BFS over RELATED_TO chains) — direct ones are surfaced as "gaps"; the goal here is new series.
# Only franchise entry points (no prequel) with a members floor, so a new series is recommended by its first season.
RECS_VA = """
    MATCH (u:User)-[l:LISTED]->(a:Anime)-[h0:HAS_CHARACTER {role: 'Main'}]->(:Character)<-[v:VOICES]-(p:Person)
    WHERE l.status <> 'plan_to_watch' AND v.language = $lang
    WITH u, p, count(DISTINCT a) AS n, avg(CASE WHEN l.score > 0 THEN toFloat(l.score) END) AS avg_score
    WHERE n >= 2
    WITH u, p, n * coalesce(avg_score, 7.0) / 10.0 AS w ORDER BY w DESC LIMIT 150
    MATCH (p)-[v2:VOICES]->(c:Character)<-[h:HAS_CHARACTER {role: 'Main'}]-(b:Anime)
    WHERE v2.language = $lang AND b.fetched_at IS NOT NULL AND NOT (u)-[:LISTED]->(b)
      AND NOT coalesce(b.seen_franchise, false)
      AND coalesce(b.members, 0) >= 5000
      AND NOT (b)-[:RELATED_TO {relation: 'Prequel'}]->(:Anime)
      AND ($min_score IS NULL OR b.score >= $min_score) AND b.type IN $types
    WITH b, sum(w) AS score, collect(DISTINCT p.name) AS people
    RETURN b, score, people[..6] AS via, size(people) AS n_people
    ORDER BY score DESC LIMIT $limit
"""
RECS_STAFF = """
    MATCH (u:User)-[l:LISTED]->(a:Anime)<-[w:WORKED_ON]-(p:Person)
    WHERE l.status <> 'plan_to_watch' AND any(pos IN w.positions WHERE pos IN $positions)
    WITH u, p, count(DISTINCT a) AS n, avg(CASE WHEN l.score > 0 THEN toFloat(l.score) END) AS avg_score
    WHERE n >= 2
    WITH u, p, n * coalesce(avg_score, 7.0) / 10.0 AS w ORDER BY w DESC LIMIT 150
    MATCH (p)-[w2:WORKED_ON]->(b:Anime)
    WHERE any(pos IN w2.positions WHERE pos IN $positions)
      AND b.fetched_at IS NOT NULL AND NOT (u)-[:LISTED]->(b)
      AND NOT coalesce(b.seen_franchise, false)
      AND coalesce(b.members, 0) >= 5000
      AND NOT (b)-[:RELATED_TO {relation: 'Prequel'}]->(:Anime)
      AND ($min_score IS NULL OR b.score >= $min_score) AND b.type IN $types
    WITH b, sum(w) AS score, collect(DISTINCT p.name) AS people
    RETURN b, score, people[..6] AS via, size(people) AS n_people
    ORDER BY score DESC LIMIT $limit
"""
RECS_STUDIO = """
    MATCH (u:User)-[l:LISTED]->(a:Anime)-[:PRODUCED_BY]->(s:Studio)
    WHERE l.status <> 'plan_to_watch'
    WITH u, s, count(DISTINCT a) AS n, avg(CASE WHEN l.score > 0 THEN toFloat(l.score) END) AS avg_score
    WHERE n >= 3
    WITH u, s, n * coalesce(avg_score, 7.0) / 10.0 AS w
    MATCH (s)<-[:PRODUCED_BY]-(b:Anime)
    WHERE b.fetched_at IS NOT NULL AND NOT (u)-[:LISTED]->(b)
      AND NOT coalesce(b.seen_franchise, false)
      AND coalesce(b.members, 0) >= 5000
      AND NOT (b)-[:RELATED_TO {relation: 'Prequel'}]->(:Anime)
      AND ($min_score IS NULL OR b.score >= $min_score) AND b.type IN $types
    WITH b, sum(w) * coalesce(b.score, 6.5) / 10.0 AS score, collect(DISTINCT s.name) AS studios
    RETURN b, score, studios AS via, size(studios) AS n_people
    ORDER BY score DESC LIMIT $limit
"""
