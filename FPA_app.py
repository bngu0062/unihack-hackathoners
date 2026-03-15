from flask import Flask, render_template, request, jsonify
import os
import urllib.request
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ── Database configuration ─────────────────────────────────────────────────
# Set DATABASE_URL for PostgreSQL (Supabase). Falls back to local SQLite.

DATABASE_URL = os.environ.get('DATABASE_URL', '')

if DATABASE_URL:
    import psycopg
    import psycopg.rows
    USE_PG = True
else:
    import sqlite3
    USE_PG = False
    DB_PATH = os.path.join(os.path.dirname(__file__), 'templates', 'database.db')


SEED_SPOTS = [
    {"lat": -37.8136, "lng": 144.9631, "a": "27 Swanston St",            "c": "Melbourne CBD, Victoria",     "co": "Australia",      "cc": "AU", "state": "Victoria",        "city": "Melbourne",     "suburb": "Melbourne CBD",    "n": "Free after 7pm, 2hr limit daytime"},
    {"lat": -33.8708, "lng": 151.2073, "a": "483 George St",              "c": "Sydney CBD, New South Wales", "co": "Australia",      "cc": "AU", "state": "New South Wales", "city": "Sydney",        "suburb": "Sydney CBD",       "n": "Free evenings after 6pm"},
    {"lat":  40.7128, "lng": -74.0060, "a": "195 Fulton St",              "c": "Lower Manhattan, New York",   "co": "USA",            "cc": "US", "state": "New York",        "city": "New York City", "suburb": "Lower Manhattan",  "n": "Free Sundays all day"},
    {"lat":  34.0522, "lng":-118.2437, "a": "350 Spring St",              "c": "Downtown LA, California",     "co": "USA",            "cc": "US", "state": "California",      "city": "Los Angeles",   "suburb": "Downtown LA",      "n": "Free after 8pm weekdays"},
    {"lat":  51.5074, "lng":  -0.1278, "a": "Victoria Embankment",        "c": "Westminster, England",        "co": "United Kingdom", "cc": "GB", "state": "England",         "city": "London",        "suburb": "Westminster",      "n": "Free evenings and Sundays"},
    {"lat":  48.8566, "lng":   2.3522, "a": "12 Boulevard de Sebastopol", "c": "Paris 1er, Île-de-France",    "co": "France",         "cc": "FR", "state": "Île-de-France",   "city": "Paris",         "suburb": "Paris 1er",        "n": "Free Sunday mornings"},
    {"lat":  35.6762, "lng": 139.6503, "a": "3 Shinjuku-dori Ave",        "c": "Shinjuku, Tokyo",             "co": "Japan",          "cc": "JP", "state": "Tokyo",           "city": "Shinjuku",      "suburb": "Shinjuku",         "n": "Free 8pm-8am daily"},
    {"lat":   1.3521, "lng": 103.8198, "a": "30 Bras Basah Rd",           "c": "City Hall, Central Region",   "co": "Singapore",      "cc": "SG", "state": "Central Region",  "city": "Singapore",     "suburb": "City Hall",        "n": "Free on Sundays"},
    {"lat":  43.6532, "lng": -79.3832, "a": "100 Bay St",                 "c": "Downtown Toronto, Ontario",   "co": "Canada",         "cc": "CA", "state": "Ontario",         "city": "Toronto",       "suburb": "Downtown Toronto", "n": "Free weekends all day"},
    {"lat": -36.8485, "lng": 174.7633, "a": "15 Queen St",                "c": "Auckland CBD, Auckland",      "co": "New Zealand",    "cc": "NZ", "state": "Auckland",        "city": "Auckland",      "suburb": "Auckland CBD",     "n": "Free after 6pm weekdays"},
]

NEED_REM = 3
NEED_DEL = 3


# ── DB connection ──────────────────────────────────────────────────────────
def get_db():
    if USE_PG:
        return psycopg.connect(DATABASE_URL, row_factory=psycopg.rows.dict_row)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Single placeholder token
PH = '%s' if DATABASE_URL else '?'


# ── Schema ─────────────────────────────────────────────────────────────────
def init_db():
    if not USE_PG:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = get_db()
    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS spots (
        id     ''' + ('SERIAL' if USE_PG else 'INTEGER') + ''' PRIMARY KEY ''' + ('' if USE_PG else 'AUTOINCREMENT') + ''',
        lat    ''' + ('DOUBLE PRECISION' if USE_PG else 'REAL') + ''' NOT NULL,
        lng    ''' + ('DOUBLE PRECISION' if USE_PG else 'REAL') + ''' NOT NULL,
        a      TEXT NOT NULL,
        c      TEXT NOT NULL DEFAULT '',
        co     TEXT NOT NULL DEFAULT '',
        cc     TEXT NOT NULL DEFAULT '',
        state  TEXT NOT NULL DEFAULT '',
        city   TEXT NOT NULL DEFAULT '',
        suburb TEXT NOT NULL DEFAULT '',
        n      TEXT NOT NULL DEFAULT '',
        up     INTEGER NOT NULL DEFAULT 0,
        dn     INTEGER NOT NULL DEFAULT 0,
        UNIQUE (lat, lng)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS votes (
        spot_id INTEGER NOT NULL,
        uid     TEXT    NOT NULL,
        vote    INTEGER NOT NULL,
        PRIMARY KEY (spot_id, uid)
    )''')

    cur.execute('''CREATE TABLE IF NOT EXISTS delete_votes (
        spot_id INTEGER NOT NULL,
        uid     TEXT    NOT NULL,
        PRIMARY KEY (spot_id, uid)
    )''')

    cur.execute('SELECT COUNT(*) AS n FROM spots')
    count = cur.fetchone()['n'] if USE_PG else cur.fetchone()[0]

    if count == 0:
        for s in SEED_SPOTS:
            cur.execute(
                'INSERT INTO spots (lat,lng,a,c,co,cc,state,city,suburb,n,up,dn) VALUES ('
                + ','.join([PH]*12) + ')',
                (s['lat'], s['lng'], s['a'], s['c'], s['co'], s['cc'],
                 s['state'], s['city'], s['suburb'], s['n'], 0, 0)
            )

    conn.commit()
    conn.close()


# ── Helper: row -> dict with vote lists ───────────────────────────────────
def spot_to_dict(row, uid=None, conn=None):
    d = dict(row)
    owns_conn = False
    if conn is None:
        conn = get_db()
        owns_conn = True
    cur = conn.cursor()

    cur.execute('SELECT uid, vote FROM votes WHERE spot_id=' + PH, (d['id'],))
    votes = cur.fetchall()
    uv = [v['uid'] for v in votes if v['vote'] == 1]
    dv = [v['uid'] for v in votes if v['vote'] == -1]
    d['uv'] = uv
    d['dv'] = dv
    d['my_vote'] = 1 if uid in uv else (-1 if uid in dv else 0)

    cur.execute('SELECT uid FROM delete_votes WHERE spot_id=' + PH, (d['id'],))
    dvotes = [r['uid'] for r in cur.fetchall()]
    d['delete_votes'] = dvotes
    d['my_delete_vote'] = (uid in dvotes) if uid else False

    if owns_conn:
        conn.close()
    return d


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('freeparking.html')


@app.route('/api/spots', methods=['GET'])
def get_spots():
    uid = request.args.get('uid', '')
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM spots')
    rows = cur.fetchall()
    result = [spot_to_dict(r, uid, conn) for r in rows]
    conn.close()
    return jsonify(result)


@app.route('/api/spots', methods=['POST'])
def add_spot():
    data = request.get_json()
    if not all(k in data for k in ['lat', 'lng', 'a']):
        return jsonify({'error': 'Missing required fields'}), 400

    conn = get_db()
    cur = conn.cursor()

    # Check for duplicate coordinates
    cur.execute(
        'SELECT id FROM spots WHERE lat=' + PH + ' AND lng=' + PH,
        (data['lat'], data['lng'])
    )
    if cur.fetchone():
        conn.close()
        return jsonify({'error': 'A spot already exists at these coordinates', 'duplicate': True}), 409

    vals = (data['lat'], data['lng'], data['a'],
            data.get('c',''), data.get('co',''), data.get('cc',''),
            data.get('state',''), data.get('city',''), data.get('suburb',''),
            data.get('n',''), 0, 0)

    if USE_PG:
        cur.execute(
            'INSERT INTO spots (lat,lng,a,c,co,cc,state,city,suburb,n,up,dn) VALUES ('
            + ','.join([PH]*12) + ') RETURNING id', vals
        )
        spot_id = cur.fetchone()['id']
    else:
        cur.execute(
            'INSERT INTO spots (lat,lng,a,c,co,cc,state,city,suburb,n,up,dn) VALUES ('
            + ','.join([PH]*12) + ')', vals
        )
        spot_id = cur.lastrowid

    conn.commit()
    cur.execute('SELECT * FROM spots WHERE id=' + PH, (spot_id,))
    result = spot_to_dict(cur.fetchone(), data.get('uid',''), conn)
    conn.close()
    return jsonify(result), 201


@app.route('/api/spots/<int:spot_id>', methods=['PUT'])
def edit_spot(spot_id):
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()

    cur.execute('SELECT * FROM spots WHERE id=' + PH, (spot_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    cur.execute(
        'UPDATE spots SET a=' + PH + ', c=' + PH + ', co=' + PH + ', cc=' + PH
        + ', state=' + PH + ', city=' + PH + ', suburb=' + PH + ', n=' + PH
        + ', up=0, dn=0 WHERE id=' + PH,
        (data.get('a', row['a']), data.get('c', row['c']),
         data.get('co', row['co']), data.get('cc', row['cc']),
         data.get('state', row['state']), data.get('city', row['city']),
         data.get('suburb', row['suburb']), data.get('n', row['n']),
         spot_id)
    )
    cur.execute('DELETE FROM votes WHERE spot_id=' + PH, (spot_id,))
    cur.execute('DELETE FROM delete_votes WHERE spot_id=' + PH, (spot_id,))
    conn.commit()

    cur.execute('SELECT * FROM spots WHERE id=' + PH, (spot_id,))
    result = spot_to_dict(cur.fetchone(), data.get('uid',''), conn)
    conn.close()
    return jsonify(result)


@app.route('/api/spots/<int:spot_id>', methods=['DELETE'])
def delete_spot(spot_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM votes WHERE spot_id=' + PH, (spot_id,))
    cur.execute('DELETE FROM delete_votes WHERE spot_id=' + PH, (spot_id,))
    cur.execute('DELETE FROM spots WHERE id=' + PH, (spot_id,))
    conn.commit()
    conn.close()
    return jsonify({'deleted': spot_id})


@app.route('/api/spots/<int:spot_id>/vote', methods=['POST'])
def vote_spot(spot_id):
    data = request.get_json()
    uid = data.get('uid', '')
    v   = data.get('vote', 0)
    if not uid or v not in (1, -1):
        return jsonify({'error': 'Invalid vote'}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute('SELECT * FROM spots WHERE id=' + PH, (spot_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    cur.execute(
        'SELECT vote FROM votes WHERE spot_id=' + PH + ' AND uid=' + PH,
        (spot_id, uid)
    )
    if cur.fetchone():
        conn.close()
        return jsonify({'error': 'Already voted'}), 409

    cur.execute(
        'INSERT INTO votes (spot_id, uid, vote) VALUES (' + ','.join([PH]*3) + ')',
        (spot_id, uid, v)
    )
    if v == 1:
        cur.execute('UPDATE spots SET up=up+1 WHERE id=' + PH, (spot_id,))
    else:
        cur.execute('UPDATE spots SET dn=dn+1 WHERE id=' + PH, (spot_id,))
    conn.commit()

    cur.execute('SELECT * FROM spots WHERE id=' + PH, (spot_id,))
    row = cur.fetchone()
    if row['dn'] >= NEED_REM:
        cur.execute('DELETE FROM votes WHERE spot_id=' + PH, (spot_id,))
        cur.execute('DELETE FROM spots WHERE id=' + PH, (spot_id,))
        conn.commit()
        conn.close()
        return jsonify({'removed': True, 'id': spot_id})

    result = spot_to_dict(row, uid, conn)
    conn.close()
    return jsonify(result)


@app.route('/api/spots/<int:spot_id>/delete-vote', methods=['POST'])
def delete_vote_spot(spot_id):
    data = request.get_json()
    uid = data.get('uid', '')
    if not uid:
        return jsonify({'error': 'uid required'}), 400

    conn = get_db()
    cur = conn.cursor()

    cur.execute('SELECT * FROM spots WHERE id=' + PH, (spot_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Not found'}), 404

    cur.execute(
        'SELECT uid FROM delete_votes WHERE spot_id=' + PH + ' AND uid=' + PH,
        (spot_id, uid)
    )
    if cur.fetchone():
        conn.close()
        return jsonify({'error': 'Already voted'}), 409

    cur.execute(
        'INSERT INTO delete_votes (spot_id, uid) VALUES (' + ','.join([PH]*2) + ')',
        (spot_id, uid)
    )
    conn.commit()

    cur.execute('SELECT COUNT(*) AS n FROM delete_votes WHERE spot_id=' + PH, (spot_id,))
    count = cur.fetchone()['n'] if USE_PG else cur.fetchone()[0]

    if count >= NEED_DEL:
        cur.execute('DELETE FROM votes WHERE spot_id=' + PH, (spot_id,))
        cur.execute('DELETE FROM delete_votes WHERE spot_id=' + PH, (spot_id,))
        cur.execute('DELETE FROM spots WHERE id=' + PH, (spot_id,))
        conn.commit()
        conn.close()
        return jsonify({'removed': True, 'id': spot_id})

    result = spot_to_dict(dict(row), uid, conn)
    result['delete_votes_count'] = count
    conn.close()
    return jsonify(result)


# ── Geocode proxies ────────────────────────────────────────────────────────
@app.route('/api/geocode', methods=['GET'])
def geocode():
    q = request.args.get('q', '')
    if not q:
        return jsonify([])
    url = ('https://nominatim.openstreetmap.org/search?format=json&limit=1'
           '&addressdetails=1&q=' + urllib.parse.quote(q))
    req = urllib.request.Request(url, headers={
        'User-Agent': 'PFA-ParkingForAll/1.0', 'Accept-Language': 'en'
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return app.response_class(resp.read(), mimetype='application/json')
    except Exception as e:
        return jsonify({'error': str(e)}), 502


@app.route('/api/reverse', methods=['GET'])
def reverse_geocode():
    lat = request.args.get('lat', '')
    lon = request.args.get('lon', '')
    if not lat or not lon:
        return jsonify({'error': 'lat/lon required'}), 400
    url = (f'https://nominatim.openstreetmap.org/reverse?format=json'
           f'&addressdetails=1&lat={lat}&lon={lon}')
    req = urllib.request.Request(url, headers={
        'User-Agent': 'PFA-ParkingForAll/1.0', 'Accept-Language': 'en'
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return app.response_class(resp.read(), mimetype='application/json')
    except Exception as e:
        return jsonify({'error': str(e)}), 502


if __name__ == '__main__':
    init_db()
    app.run(debug=False, host='0.0.0.0')