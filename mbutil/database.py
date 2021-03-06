import psycopg2, sqlite3, oursql, pymongo, bson, uuid, sys, logging, time, os, json, zlib, hashlib, tempfile, math

logger = logging.getLogger(__name__)


def database_connect(connect_string, auto_commit=False, journal_mode='wal', synchronous_off=False, exclusive_lock=False, check_if_exists=False):
    """Connect to a database
    """

    if connect_string.endswith(".mbtiles"):
        return MBTilesSQLite(connect_string, auto_commit, journal_mode, synchronous_off, exclusive_lock, check_if_exists)
    elif connect_string.find("driver=postgres") >= 0 or connect_string.startswith("pg:"):
        return MBTilesPostgres(connect_string.replace("driver=postgres", ""), auto_commit, journal_mode, synchronous_off, exclusive_lock, check_if_exists)
    elif connect_string.find("driver=mysql") >= 0 or connect_string.startswith("my:"):
        return MBTilesMySQL(connect_string.replace("driver=mysql", ""), auto_commit, journal_mode, synchronous_off, exclusive_lock, check_if_exists)
    elif connect_string.find("driver=mongodb") >= 0 or connect_string.startswith("mongodb:"):
        return MBTilesMongoDB(connect_string.replace("driver=mongodb", ""), auto_commit, journal_mode, synchronous_off, exclusive_lock, check_if_exists)
    else:
        logger.error("Unknown database connection string")
        sys.exit(1)



class MBTilesDatabase:

    def __init__(self, connect_string, auto_commit=False, journal_mode='wal', synchronous_off=False, exclusive_lock=False, check_if_exists=False):
        self.connect_string = connect_string
        self.con = None
        self.cur = None
        self.database_is_compacted = None
        self.database_has_scale = None

    def close(self):
        self.con.commit()
        self.con.close()

    def mbtiles_setup(self):
        raise Exception("Not implemented.")

    def optimize_database(self, skip_analyze, skip_vacuum):
        if not skip_analyze:
            logger.info('analyzing db')
            self.cur.execute("""ANALYZE""")

        if not skip_vacuum:
            logger.info('cleaning db')
            self.cur.execute("""VACUUM""")

    def create_map_tile_index(self):
        raise Exception("Not implemented.")

    def drop_map_tile_index(self):
        raise Exception("Not implemented.")

    def execute(self, sql):
        self.cur.execute(sql)

    def is_compacted(self):
        return True

    def has_scale(self):
        return True

    def max_timestamp(self):
        raise Exception("Not implemented.")

    # Returns an array with numbers, e.g. [5, 6, 7]
    def zoom_levels(self, scale):
        raise Exception("Not implemented.")

    def tiles_count(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        raise Exception("Not implemented.")

    # Yields [x, y]
    def columns_and_rows_for_zoom_level(self, zoom_level, scale):
        raise Exception("Not implemented.")

    # Yields [x]
    def columns_for_zoom_level_and_row(self, zoom_level, row, scale):
        raise Exception("Not implemented.")

    # Yields [z, x, y, data]
    def tiles(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        raise Exception("Not implemented.")

    # Yields [z, x, y, data, tile_id]
    def tiles_with_tile_id(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        raise Exception("Not implemented.")

    # Yields [z, x, y, data, tile_id]
    def updates(self, min_zoom, max_zoom, min_timestamp, max_timestamp):
        raise Exception("Not implemented.")

    def updates_count(self, min_zoom, max_zoom, min_timestamp, max_timestamp):
        raise Exception("Not implemented.")

    def delete_tiles(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        raise Exception("Not implemented.")

    def expire_tiles(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        raise Exception("Not implemented.")

    def expire_tile(self, tile_z, tile_x, tile_y, scale):
        raise Exception("Not implemented.")

    def delete_orphaned_images(self):
        self.cur.execute("DELETE FROM images WHERE tile_id NOT IN (SELECT distinct(tile_id) FROM map)")

    # Returns minX, maxX, minY, maxY
    def bounding_box_for_zoom_level(self, zoom_level, scale):
        raise Exception("Not implemented.")

    def delete_tile_with_id(self, tile_id):
        raise Exception("Not implemented.")

    def insert_tile_to_images(self, tile_id, tile_data):
        raise Exception("Not implemented.")

    # tile_list must be an array of (tile_id, tile_data)
    def insert_tiles_to_images(self, tile_list):
        raise Exception("Not implemented.")

    def insert_tile_to_map(self, zoom_level, tile_column, tile_row, tile_scale, tile_id, replace_existing=True):
        raise Exception("Not implemented.")

    # tile_list must be an array of (z, x, y, scale, tile_id, timestamp)
    def insert_tiles_to_map(self, tile_list):
        raise Exception("Not implemented.")

    def insert_tile(self, zoom_level, tile_column, tile_row, tile_scale, tile_data):
        raise Exception("Not implemented.")

    # tile_list must be an array of (z, x, y, scale, tile_data, timestamp)
    def insert_tiles(self, tile_list):
        raise Exception("Not implemented.")

    def update_tile(self, old_tile_id, new_tile_id, tile_data):
        raise Exception("Not implemented.")

    def metadata(self):
        raise Exception("Not implemented.")

    def update_metadata(self, key, value):
        raise Exception("Not implemented.")



class MBTilesSQLite(MBTilesDatabase):

    def __init__(self, connect_string, auto_commit=False, journal_mode='wal', synchronous_off=False, exclusive_lock=False, check_if_exists=False):
        self.connect_string = connect_string
        self.database_is_compacted = None
        self.database_has_scale = None

        if check_if_exists and not os.path.isfile(connect_string):
            sys.stderr.write('The mbtiles database must exist.\n')
            sys.exit(1)

        try:

            self.con = sqlite3.connect(connect_string)
            if auto_commit:
                self.con.isolation_level = None

            self.cur = self.con.cursor()

            self.cur.execute("PRAGMA cache_size = 100000")
            self.cur.execute("PRAGMA temp_store = memory")
            self.cur.execute("PRAGMA count_changes = OFF")
            self.cur.execute("PRAGMA synchronous = NORMAL")

            try:
                self.cur.execute("PRAGMA journal_mode = '%s'" % (journal_mode))
            except sqlite3.OperationalError:
                logger.error("Could not set journal_mode='%s'" % (journal_mode))
                pass

            if exclusive_lock:
                self.cur.execute("PRAGMA locking_mode = EXCLUSIVE")

            if synchronous_off:
                self.cur.execute("PRAGMA synchronous = OFF")

        except Exception, e:
            logger.error("Could not connect to the SQLite database:")
            logger.error(e)
            sys.exit(1)


    def mbtiles_setup(self):
        self.cur.execute("PRAGMA page_size = 4096")

        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS images (
            tile_id VARCHAR(256),
            tile_data BLOB )""")
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS map (
            zoom_level INTEGER,
            tile_column INTEGER,
            tile_row INTEGER,
            tile_scale TINYINT,
            tile_id VARCHAR(256),
            updated_at INTEGER )""")
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
            name VARCHAR(256),
            value TEXT )""")
        self.cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS name ON metadata (name)""")

        try:
            self.cur.execute("""
                ALTER TABLE map ADD COLUMN
                tile_scale TINYINT default 1""")
            self.cur.execute("""
                DROP INDEX map_index""")
        except sqlite3.OperationalError:
            pass

        try:
            self.cur.execute("""
                ALTER TABLE map ADD COLUMN
                updated_at INTEGER""")
        except sqlite3.OperationalError:
            pass

        try:
            self.cur.execute("""DROP VIEW tiles""")
        except sqlite3.OperationalError:
            pass

        self.cur.execute("""
            CREATE VIEW tiles AS
            SELECT map.zoom_level AS zoom_level,
            map.tile_column AS tile_column,
            map.tile_row AS tile_row,
            map.tile_scale AS tile_scale,
            images.tile_data AS tile_data,
            map.updated_at AS updated_at
            FROM map
            JOIN images
            ON map.tile_id IS NOT NULL AND images.tile_id = map.tile_id""")
        self.cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS map_index ON map
            (zoom_level, tile_column, tile_row, tile_scale)""")
        self.cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS images_id ON images (tile_id)""")


    def create_map_tile_index(self):
        self.cur.execute("""CREATE INDEX IF NOT EXISTS map_tile_id_index ON map (tile_id)""")


    def drop_map_tile_index(self):
        self.cur.execute("""DROP INDEX map_tile_id_index""")


    def is_compacted(self):
        if self.database_is_compacted == None:
            self.database_is_compacted = (self.cur.execute("SELECT count(name) FROM sqlite_master WHERE type='table' AND (name='images' OR name='map')").fetchone()[0] == 2)
        return self.database_is_compacted


    def has_scale(self):
        if self.database_has_scale == None:
            try:
                self.cur.execute("SELECT tile_scale FROM map LIMIT 1")
                self.database_has_scale = True
            except sqlite3.OperationalError:
                self.database_has_scale = False
        return self.database_has_scale

    def max_timestamp(self):
        try:
            return self.cur.execute("SELECT max(updated_at) FROM map").fetchone()[0]
        except:
            return 0


    def zoom_levels(self, scale):
        sql = "SELECT distinct(zoom_level) FROM tiles "

        if scale:
            sql += " WHERE tile_scale=%d " % (scale,)

        return [int(x[0]) for x in self.cur.execute(sql).fetchall()]


    def tiles_count(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        sql = "SELECT count(zoom_level) FROM map WHERE "

        if min_zoom > 0:
            sql += " zoom_level>=%d AND " % (min_zoom,)
        if max_zoom < 18:
            sql += " zoom_level<=%d AND " % (max_zoom,)

        if self.has_scale() and scale is not None:
            sql += " tile_scale=%d AND " % (scale,)

        if self.is_compacted():
            if min_timestamp > 0:
                sql += " updated_at>%d AND " % (min_timestamp,)
            if max_timestamp > 0:
                sql += " updated_at<%d AND " % (max_timestamp,)

            sql += " tile_id IS NOT NULL"

        logger.debug(sql)

        return self.cur.execute(sql).fetchone()[0]


    def columns_and_rows_for_zoom_level(self, zoom_level, scale):
        tiles_cur = self.con.cursor()

        sql = "SELECT tile_column, tile_row FROM map WHERE zoom_level=%d " % (zoom_level,)

        if self.has_scale() and scale is not None:
            sql += " AND tile_scale=%d " % (scale,)

        tiles = tiles_cur.execute(sql)

        t = tiles.fetchone()
        while t:
            yield t
            t = tiles.fetchone()

        tiles_cur.close()


    def columns_for_zoom_level_and_row(self, zoom_level, row, scale):
        sql = "SELECT tile_column FROM tiles WHERE zoom_level=%d AND tile_row=%d" % (zoom_level, row)

        if self.has_scale() and scale is not None:
            sql += " AND tile_scale=%d " % (scale,)

        return set([int(x[0]) for x in self.cur.execute(sql).fetchall()])


    def tiles_with_tile_id(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        tiles_cur = self.con.cursor()

        chunk = 10000

        sql = "SELECT map.zoom_level, map.tile_column, map.tile_row, "

        if self.has_scale():
            sql +=  "map.tile_scale, "
        elif scale is not None:
            sql += "%d, " % (scale,)
        else:
            sql += "1, "

        sql += "images.tile_data, images.tile_id FROM map, images WHERE "

        inner_sql = ""

        if min_zoom > 0:
            inner_sql += " map.zoom_level>=%d " % (min_zoom,)
        if max_zoom < 18:
            if len(inner_sql) > 0:
                inner_sql += " AND "
            inner_sql += " map.zoom_level<=%d " % (max_zoom,)

        if self.has_scale() and scale is not None:
            if len(inner_sql) > 0:
                inner_sql += " AND "
            inner_sql += " tile_scale=%d " % (scale,)

        if min_timestamp > 0:
            if len(inner_sql) > 0:
                inner_sql += " AND "
            inner_sql += " map.updated_at>%d " % (min_timestamp,)
        if max_timestamp > 0:
            if len(inner_sql) > 0:
                inner_sql += " AND "
            inner_sql += " map.updated_at<%d " % (max_timestamp,)

        if len(inner_sql) > 0:
            sql += " (%s) AND " % (inner_sql,)
        sql += " (map.tile_id IS NOT NULL) AND (images.tile_id == map.tile_id) "

        logger.debug(sql)

        tiles_cur.execute(sql)

        rows = tiles_cur.fetchmany(chunk)
        while rows:
            for t in rows:
                yield t
            rows = tiles_cur.fetchmany(chunk)

        tiles_cur.close()


    def tiles(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        tiles_cur = self.con.cursor()

        chunk = 10000

        sql = "SELECT zoom_level, tile_column, tile_row, "

        if self.has_scale():
            sql +=  "tile_scale, "
        elif scale is not None:
            sql += "%d, " % (scale,)
        else:
            sql += "1, "

        sql += " tile_data FROM tiles WHERE "

        if min_zoom > 0:
            sql += " zoom_level>=%d AND " % (min_zoom,)
        if max_zoom < 18:
            sql += " zoom_level<=%d AND " % (max_zoom,)

        if self.has_scale() and scale is not None:
            sql += " tile_scale=%d AND " % (scale,)

        if self.is_compacted():
            if min_timestamp > 0:
                sql += " updated_at>%d AND " % (min_timestamp,)
            if max_timestamp > 0:
                sql += " updated_at<%d AND " % (max_timestamp,)

        sql += " 1 "

        logger.debug(sql)

        tiles_cur.execute(sql)

        rows = tiles_cur.fetchmany(chunk)
        while rows:
            for t in rows:
                yield t
            rows = tiles_cur.fetchmany(chunk)

        tiles_cur.close()


    def updates(self, min_zoom, max_zoom, min_timestamp, max_timestamp):
        tiles_cur = self.con.cursor()

        chunk = 10000

        tiles_cur.execute("""
            SELECT map.zoom_level, map.tile_column, map.tile_row, map.tile_scale, images.tile_data, images.tile_id
            FROM map, images
            WHERE (map.zoom_level>=? and map.zoom_level<=? AND map.updated_at>? AND map.updated_at<?) AND (images.tile_id == map.tile_id)
            UNION
            SELECT map.zoom_level, map.tile_column, map.tile_row, map.tile_scale, NULL, NULL
            FROM map
            WHERE (map.zoom_level>=? and map.zoom_level<=? AND map.updated_at>? AND map.updated_at<?) AND (map.tile_id IS NULL)
            """,
            (min_zoom, max_zoom, min_timestamp, max_timestamp, min_zoom, max_zoom, min_timestamp, max_timestamp))

        rows = tiles_cur.fetchmany(chunk)
        while rows:
            for t in rows:
                yield t
            rows = tiles_cur.fetchmany(chunk)

        tiles_cur.close()


    def updates_count(self, min_zoom, max_zoom, min_timestamp, max_timestamp):
        total_tiles = self.cur.execute("""SELECT count(zoom_level) FROM map WHERE zoom_level>=? AND zoom_level<=? AND updated_at>? AND updated_at<?""",
            (min_zoom, max_zoom, min_timestamp, max_timestamp)).fetchone()[0]

        return total_tiles


    def delete_tiles(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        if self.is_compacted():
            sql_images = "SELECT tile_id FROM map WHERE zoom_level>=%d AND zoom_level<=%d " % (min_zoom, max_zoom)
            sql_map = "DELETE FROM map WHERE zoom_level>=%d AND zoom_level<=%d " % (min_zoom, max_zoom)

            if self.has_scale() and scale is not None:
                sql_images += " AND tile_scale=%d " % (scale,)
                sql_map += " AND tile_scale=%d " % (scale,)

            if min_timestamp > 0:
                sql_images += " AND updated_at>%d " % (min_timestamp,)
                sql_map += " AND updated_at>%d " % (min_timestamp,)
            if max_timestamp > 0:
                sql_images += " AND updated_at<%d " (max_timestamp,)
                sql_map += " AND updated_at<%d " % (max_timestamp,)

            self.cur.execute("DELETE FROM images WHERE tile_id IN (%s)" % (sql_images,))
            self.cur.execute(sql_map)

        else:
            sql += "DELETE FROM tiles WHERE zoom_level>=%d AND zoom_level<=%d " % (min_zoom, max_zoom)

            if self.has_scale() and scale is not None:
                sql += " AND tile_scale=%d " % (scale,)

            self.cur.execute(sql)


    def expire_tiles(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        if not self.is_compacted():
            self.delete_tiles(min_zoom, max_zoom, min_timestamp, max_timestamp, scale)
            return

        sql_images = "SELECT tile_id FROM map WHERE zoom_level>=%d AND zoom_level<=%d " % (min_zoom, max_zoom)
        sql_map = "UPDATE map SET tile_id=NULL, updated_at=%d WHERE zoom_level>=%d AND zoom_level<=%d " % (int(time.time()), min_zoom, max_zoom)

        if self.has_scale() and scale is not None:
            sql_images += " AND tile_scale=%d " % (scale,)
            sql_map += " AND tile_scale=%d " % (scale,)

        if min_timestamp > 0:
            sql_images += " AND updated_at>%d " % (min_timestamp,)
            sql_map += " AND updated_at>%d " % (min_timestamp,)
        if max_timestamp > 0:
            sql_images += " AND updated_at<%d " % (max_timestamp,)
            sql_map += " AND updated_at<%d " % (max_timestamp,)

        self.cur.execute("DELETE FROM images WHERE tile_id IN (%s)" % (sql_images,))
        self.cur.execute(sql_map)


    def expire_tile(self, tile_z, tile_x, tile_y, scale):
        if self.is_compacted():
            sql_images = "SELECT tile_id FROM map WHERE zoom_level=%d AND tile_column=%d AND tile_row=%d " % (tile_z, tile_x, tile_y)
            sql_map = "UPDATE map SET tile_id=NULL, updated_at=%d WHERE zoom_level=%d AND tile_column=%d AND tile_row=%d " % (int(time.time()), tile_z, tile_x, tile_y)

            if self.has_scale() and scale is not None:
                sql_images += " AND tile_scale=%d " % (scale,)
                sql_map += " AND tile_scale=%d " % (scale,)

            self.cur.execute("DELETE FROM images WHERE tile_id IN (%s)" % (sql_images,))
            self.cur.execute(sql_map)

        else:
            sql = "DELETE FROM tiles WHERE zoom_level=%d AND tile_column=%d AND tile_row=%d " % (tile_z, tile_x, tile_y)

            if self.has_scale() and scale is not None:
                sql += " AND tile_scale=%d " % (scale,)

            self.cur.execute(sql)


    def bounding_box_for_zoom_level(self, zoom_level, scale):
        sql = "SELECT min(tile_column), max(tile_column), min(tile_row), max(tile_row) FROM tiles WHERE zoom_level=%d " % (zoom_level,)

        if self.has_scale() and scale is not None:
            sql += " AND tile_scale=%d " % (scale,)

        return self.cur.execute(sql).fetchone()


    def delete_tile_with_id(self, tile_id):
        self.cur.execute("""DELETE FROM map WHERE tile_id=?""", (tile_id, ));
        self.cur.execute("""DELETE FROM images WHERE tile_id=?""", (tile_id, ))


    def insert_tile_to_images(self, tile_id, tile_data):
        self.cur.execute("""INSERT OR IGNORE INTO images (tile_id, tile_data) VALUES (?, ?)""",
            (tile_id, sqlite3.Binary(tile_data)))


    def insert_tiles_to_images(self, tile_list):
        self.cur.executemany("""INSERT OR IGNORE INTO images (tile_id, tile_data) VALUES (?, ?)""", [(t[0], sqlite3.Binary(t[1])) for t in tile_list])


    def insert_tile_to_map(self, zoom_level, tile_column, tile_row, tile_scale, tile_id, replace_existing=True):
        if replace_existing:
            if self.has_scale():
                self.cur.execute("""REPLACE INTO map (zoom_level, tile_column, tile_row, tile_scale, tile_id, updated_at) VALUES (?, ?, ?, ?, ?, ?)""",
                    (zoom_level, tile_column, tile_row, tile_scale, tile_id, int(time.time())))
            else:
                self.cur.execute("""REPLACE INTO map (zoom_level, tile_column, tile_row, tile_id, updated_at) VALUES (?, ?, ?, ?, ?)""",
                    (zoom_level, tile_column, tile_row, tile_id, int(time.time())))
        else:
            if self.has_scale():
                self.cur.execute("""INSERT OR IGNORE INTO map (zoom_level, tile_column, tile_row, tile_scale, tile_id, updated_at) VALUES (?, ?, ?, ?, ?, ?)""",
                    (zoom_level, tile_column, tile_row, tile_scale, tile_id, int(time.time())))
            else:
                self.cur.execute("""INSERT OR IGNORE INTO map (zoom_level, tile_column, tile_row, tile_id, updated_at) VALUES (?, ?, ?, ?, ?)""",
                    (zoom_level, tile_column, tile_row, tile_id, int(time.time())))


    def insert_tiles_to_map(self, tile_list):
        if self.has_scale():
            self.cur.executemany("""REPLACE INTO map (zoom_level, tile_column, tile_row, tile_scale, tile_id, updated_at) VALUES (?, ?, ?, ?, ?, ?)""", tile_list)
        else:
            self.cur.executemany("""REPLACE INTO map (zoom_level, tile_column, tile_row, tile_id, updated_at) VALUES (?, ?, ?, ?, ?)""", tile_list)


    def update_tile(self, old_tile_id, new_tile_id, tile_data):
        self.cur.execute("""INSERT OR IGNORE INTO images (tile_id, tile_data) VALUES (?, ?)""",
            (new_tile_id, sqlite3.Binary(tile_data)))
        self.cur.execute("""UPDATE map SET tile_id=?, updated_at=? WHERE tile_id=?""",
            (new_tile_id, int(time.time()), old_tile_id))

        if old_tile_id != new_tile_id:
            self.cur.execute("""DELETE FROM images WHERE tile_id=?""",
                [old_tile_id])


    def metadata(self):
        try:
            return dict(self.cur.execute('SELECT name, value FROM metadata').fetchall())
        except Exception, e:
            return None


    def update_metadata(self, key, value):
        self.cur.execute('REPLACE INTO metadata (name, value) VALUES (?, ?)',
            (key, value))



class MBTilesPostgres(MBTilesDatabase):

    def __init__(self, connect_string, auto_commit=False, journal_mode='wal', synchronous_off=False, exclusive_lock=False, check_if_exists=False):
        self.database_has_scale = None

        try:

            if connect_string.startswith("pg:"):
                if os.path.isfile("/etc/mb-util.conf"):
                    config = {}

                    with open("/etc/mb-util.conf") as f:
                        for line in f:
                            try:
                                for (key, value) in (line.strip().split(":", 1),):
                                    config[key.strip()] = value.strip()
                            except:
                                pass

                    key = connect_string.split(':')[1]
                    if len(key):
                        if config.get(key, None) != None:
                            connect_string = config.get(key, connect_string)
                        else:
                            logger.error("Could not find '%s' in /etc/mb-util.conf." % (key))
                            sys.exit(1)

            self.connect_string = connect_string
            self.con = psycopg2.connect(connect_string)

            # autocommit is always enabled in PostgreSQL since it makes lots of things easier
            # until Postgres has an upsert method
            # if auto_commit:
            self.con.autocommit = True

            self.cur = self.con.cursor()

            if check_if_exists:
                self.cur.execute("SELECT count(*) FROM pg_tables WHERE tablename = 'map'")
                if self.cur.fetchone()[0] == 0:
                    self.close()
                    sys.stderr.write('The mbtiles database and tables must exist.\n')
                    sys.exit(1)

        except Exception, e:
            logger.error("Could not connect to the PostgreSQL database '%s':" % (connect_string))
            logger.error(e)
            sys.exit(1)


    def mbtiles_setup(self):
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS images (
            tile_id VARCHAR(256),
            tile_data BYTEA )""")
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS map (
            zoom_level SMALLINT,
            tile_column INTEGER,
            tile_row INTEGER,
            tile_scale SMALLINT,
            tile_id VARCHAR(256),
            updated_at INTEGER )""")
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
            name VARCHAR(256),
            value TEXT )""")

        self.cur.execute("SELECT count(*) FROM pg_class WHERE relname = 'metadata_name_index'")
        if self.cur.fetchone()[0] == 0:
            self.cur.execute("""CREATE UNIQUE INDEX metadata_name_index ON metadata (name)""")

        if self.has_scale():
            self.cur.execute("""
                CREATE OR REPLACE VIEW tiles AS
                SELECT map.zoom_level AS zoom_level,
                map.tile_column AS tile_column,
                map.tile_row AS tile_row,
                map.tile_scale AS tile_scale,
                images.tile_data AS tile_data,
                map.updated_at AS updated_at
                FROM map
                JOIN images
                ON map.tile_id IS NOT NULL AND images.tile_id = map.tile_id""")
        else:
            self.cur.execute("""
                CREATE OR REPLACE VIEW tiles AS
                SELECT map.zoom_level AS zoom_level,
                map.tile_column AS tile_column,
                map.tile_row AS tile_row,
                images.tile_data AS tile_data,
                map.updated_at AS updated_at
                FROM map
                JOIN images
                ON map.tile_id IS NOT NULL AND images.tile_id = map.tile_id""")

        self.cur.execute("SELECT count(*) FROM pg_class WHERE relname = 'map_coordinate_index'")
        if self.cur.fetchone()[0] == 0:
            if self.has_scale():
                self.cur.execute("""CREATE UNIQUE INDEX map_coordinate_index ON map (zoom_level, tile_column, tile_row, tile_scale)""")
            else:
                self.cur.execute("""CREATE UNIQUE INDEX map_coordinate_index ON map (zoom_level, tile_column, tile_row)""")

        self.cur.execute("SELECT count(*) FROM pg_class WHERE relname = 'images_id_index'")
        if self.cur.fetchone()[0] == 0:
            self.cur.execute("""CREATE UNIQUE INDEX images_id_index ON images (tile_id)""")

        # From http://www.postgresql.org/docs/current/static/plpgsql-control-structures.html#PLPGSQL-UPSERT-EXAMPLE
        self.cur.execute("SELECT count(*) FROM pg_proc WHERE proname = 'update_map_proc'")
        if self.cur.fetchone()[0] == 0:
            self.cur.execute("""
                CREATE OR REPLACE FUNCTION update_map_proc(tile_z INTEGER, tile_x INTEGER, tile_y INTEGER, scale SMALLINT, key VARCHAR,
            updated_timestamp INTEGER) RETURNS VOID AS
                $$
                BEGIN
                    LOOP
                        UPDATE map SET tile_id = key, updated_at = updated_timestamp WHERE zoom_level = tile_z AND tile_column = tile_x and tile_row = tile_y and tile_scale = scale;
                        IF found THEN
                            RETURN;
                        END IF;
                        BEGIN
                            INSERT INTO map(zoom_level, tile_column, tile_row, tile_scale, tile_id, updated_at) VALUES (tile_z, tile_x, tile_y, scale, key, updated_timestamp);
                            RETURN;
                        EXCEPTION WHEN unique_violation THEN
                        END;
                    END LOOP;
                END;
                $$
                LANGUAGE plpgsql""")

        if not self.has_scale():
            self.cur.execute("""
                CREATE OR REPLACE FUNCTION update_map_proc(tile_z INTEGER, tile_x INTEGER, tile_y INTEGER, key VARCHAR,
            updated_timestamp INTEGER) RETURNS VOID AS
                $$
                BEGIN
                    LOOP
                        UPDATE map SET tile_id = key, updated_at = updated_timestamp WHERE zoom_level = tile_z AND tile_column = tile_x and tile_row = tile_y;
                        IF found THEN
                            RETURN;
                        END IF;
                        BEGIN
                            INSERT INTO map(zoom_level, tile_column, tile_row, tile_id, updated_at) VALUES (tile_z, tile_x, tile_y, key, updated_timestamp);
                            RETURN;
                        EXCEPTION WHEN unique_violation THEN
                        END;
                    END LOOP;
                END;
                $$
                LANGUAGE plpgsql""")


    def has_scale(self):
        if self.database_has_scale == None:
            try:
                self.cur.execute("SELECT tile_scale FROM map LIMIT 1")
                self.database_has_scale = True
            except Exception, e:
                self.database_has_scale = False
        return self.database_has_scale


    def create_map_tile_index(self):
        self.cur.execute("SELECT count(*) FROM pg_class WHERE relname = 'map_tile_id_index'")
        if self.cur.fetchone()[0] == 0:
            self.cur.execute("""CREATE INDEX map_tile_id_index ON map (tile_id)""")


    def drop_map_tile_index(self):
        self.cur.execute("""DROP INDEX map_tile_id_index""")


    def max_timestamp(self):
        self.cur.execute("SELECT max(updated_at) FROM map")
        result = self.cur.fetchone()

        if not result:
            return 0

        return result[0]


    def zoom_levels(self, scale):
        sql = "SELECT distinct(zoom_level) FROM tiles "

        if scale is not None:
            sql += " WHERE tile_scale=%d " % (scale,)

        self.cur.execute(sql)
        return [int(x[0]) for x in self.cur.fetchall()]


    def tiles_count(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        sql = "SELECT count(zoom_level) FROM map WHERE "

        if min_zoom > 0:
            sql += " zoom_level>=%d AND " % (min_zoom,)
        if max_zoom < 18:
            sql += " zoom_level<=%d AND " % (max_zoom,)

        if self.has_scale() and scale is not None:
            sql += " tile_scale=%d AND " % (scale,)

        if min_timestamp > 0:
            sql += " updated_at>%d AND " % (min_timestamp,)
        if max_timestamp > 0:
            sql += " updated_at<%d AND " % (max_timestamp,)

        sql += " tile_id IS NOT NULL"

        logger.debug(sql)

        self.cur.execute(sql)

        return self.cur.fetchone()[0]


    def columns_and_rows_for_zoom_level(self, zoom_level, scale):
        tiles_cur = self.con.cursor()

        sql = "SELECT tile_column, tile_row FROM map WHERE zoom_level=%d " % (zoom_level,)

        if self.has_scale() and scale is not None:
            sql += " AND tile_scale=%d " % (scale,)

        tiles = tiles_cur.execute(sql)

        t = tiles_cur.fetchone()
        while t:
            yield t
            t = tiles_cur.fetchone()

        tiles_cur.close()


    def columns_for_zoom_level_and_row(self, zoom_level, row, scale):
        sql = "SELECT tile_column FROM tiles WHERE zoom_level=%d AND tile_row=%d" % (zoom_level, row)

        if self.has_scale() and scale is not None:
            sql += " AND tile_scale=%d " % (scale,)

        self.cur.execute(sql)

        return set([int(x[0]) for x in self.cur.fetchall()])


    def tiles_with_tile_id(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        # Second connection to the database, for the named cursor
        iter_con = psycopg2.connect(self.connect_string)

        tiles_cur = iter_con.cursor("tiles_with_tile_id_cursor")

        sql = "SELECT map.zoom_level, map.tile_column, map.tile_row, "

        if self.has_scale():
            sql +=  "map.tile_scale, "
        elif scale is not None:
            sql += "%d, " % (scale,)
        else:
            sql += "1, "

        sql += "images.tile_data, images.tile_id FROM map, images WHERE "

        inner_sql = ""

        if min_zoom > 0:
            inner_sql += " map.zoom_level>=%d " % (min_zoom,)
        if max_zoom < 18:
            if len(inner_sql) > 0:
                inner_sql += " AND "
            inner_sql += " map.zoom_level<=%d " % (max_zoom,)

        if self.has_scale() and scale is not None:
            if len(inner_sql) > 0:
                inner_sql += " AND "
            inner_sql += " tile_scale=%d " % (scale,)

        if min_timestamp > 0:
            if len(inner_sql) > 0:
                inner_sql += " AND "
            inner_sql += " map.updated_at>%d " % (min_timestamp,)
        if max_timestamp > 0:
            if len(inner_sql) > 0:
                inner_sql += " AND "
            inner_sql += " map.updated_at<%d " % (max_timestamp,)

        if len(inner_sql) > 0:
            sql += " (%s) AND " % (inner_sql,)
        sql += " (map.tile_id IS NOT NULL) AND (images.tile_id = map.tile_id) "

        logger.debug(sql)

        tiles_cur.execute(sql)

        t = tiles_cur.fetchone()
        while t:
            yield t
            t = tiles_cur.fetchone()

        tiles_cur.close()
        iter_con.close()


    def tiles(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        # Second connection to the database, for the named cursor
        iter_con = psycopg2.connect(self.connect_string)

        tiles_cur = iter_con.cursor("tiles_cursor")

        sql = "SELECT zoom_level, tile_column, tile_row, "

        if self.has_scale():
            sql +=  "tile_scale, "
        elif scale is not None:
            sql += "%d, " % (scale,)
        else:
            sql += "1, "

        sql += " tile_data FROM tiles WHERE "

        if min_zoom > 0:
            sql += " zoom_level>=%d AND " % (min_zoom,)
        if max_zoom < 18:
            sql += " zoom_level<=%d AND " % (max_zoom,)

        if self.has_scale() and scale is not None:
            sql += " tile_scale=%d AND " % (scale,)

        if min_timestamp > 0:
            sql += " updated_at>%d AND " % (min_timestamp,)
        if max_timestamp > 0:
            sql += " updated_at<%d AND " % (max_timestamp,)

        sql += " 1 "

        logger.debug(sql)

        tiles_cur.execute(sql)

        t = tiles_cur.fetchone()
        while t:
            yield t
            t = tiles_cur.fetchone()

        tiles_cur.close()
        iter_con.close()


    def updates(self, min_zoom, max_zoom, min_timestamp, max_timestamp):
        # Second connection to the database, for the named cursor
        iter_con = psycopg2.connect(self.connect_string)

        tiles_cur = iter_con.cursor("tiles_with_tile_id_cursor")

        tiles_cur.execute("""
            SELECT map.zoom_level, map.tile_column, map.tile_row, map.tile_scale, images.tile_data, images.tile_id
            FROM map, images
            WHERE (map.zoom_level>=%s and map.zoom_level<=%s AND map.updated_at>%s AND map.updated_at<%s) AND (images.tile_id = map.tile_id)
            UNION
            SELECT map.zoom_level, map.tile_column, map.tile_row, map.tile_scale, NULL, NULL
            FROM map
            WHERE (map.zoom_level>=%s and map.zoom_level<=%s AND map.updated_at>%s AND map.updated_at<%s) AND map.tile_id IS NULL
            """,
            (min_zoom, max_zoom, min_timestamp, max_timestamp, min_zoom, max_zoom, min_timestamp, max_timestamp))

        t = tiles_cur.fetchone()
        while t:
            yield t
            t = tiles_cur.fetchone()

        tiles_cur.close()
        iter_con.close()


    def updates_count(self, min_zoom, max_zoom, min_timestamp, max_timestamp):
        self.cur.execute("""SELECT count(zoom_level) FROM map WHERE zoom_level>=%s AND zoom_level<=%s AND updated_at>%s AND updated_at<%s""",
            (min_zoom, max_zoom, min_timestamp, max_timestamp))

        return self.cur.fetchone()[0]


    def delete_tiles(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        sql_images = "SELECT tile_id FROM map WHERE zoom_level>=%d AND zoom_level<=%d " % (min_zoom, max_zoom)
        sql_map = "DELETE FROM map WHERE zoom_level>=%d AND zoom_level<=%d " % (min_zoom, max_zoom)

        if self.has_scale() and scale is not None:
            sql_images += " AND tile_scale=%d " % (scale,)
            sql_map += " AND tile_scale=%d " % (scale,)

        if min_timestamp > 0:
            sql_images += " AND updated_at>%d " % (min_timestamp,)
            sql_map += " AND updated_at>%d " % (min_timestamp,)
        if max_timestamp > 0:
            sql_images += " AND updated_at<%d " (max_timestamp,)
            sql_map += " AND updated_at<%d " % (max_timestamp,)

        self.cur.execute("DELETE FROM images WHERE tile_id IN (%s)" % (sql_images,))
        self.cur.execute(sql_map)


    def expire_tiles(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        sql_images = "SELECT tile_id FROM map WHERE zoom_level>=%d AND zoom_level<=%d " % (min_zoom, max_zoom)
        sql_map = "UPDATE map SET tile_id=NULL, updated_at=%d WHERE zoom_level>=%d AND zoom_level<=%d " % (int(time.time()), min_zoom, max_zoom)

        if self.has_scale() and scale is not None:
            sql_images += " AND tile_scale=%d " % (scale,)
            sql_map += " AND tile_scale=%d " % (scale,)

        if min_timestamp > 0:
            sql_images += " AND updated_at>%d " % (min_timestamp,)
            sql_map += " AND updated_at>%d " % (min_timestamp,)
        if max_timestamp > 0:
            sql_images += " AND updated_at<%d " % (max_timestamp,)
            sql_map += " AND updated_at<%d " % (max_timestamp,)

        self.cur.execute("DELETE FROM images WHERE tile_id IN (%s)" % (sql_images,))
        self.cur.execute(sql_map)


    def expire_tile(self, tile_z, tile_x, tile_y, scale):
        sql_images = "SELECT tile_id FROM map WHERE zoom_level=%d AND tile_column=%d AND tile_row=%d " % (tile_z, tile_x, tile_y)
        sql_map = "UPDATE map SET tile_id=NULL, updated_at=%d WHERE zoom_level=%d AND tile_column=%d AND tile_row=%d " % (int(time.time()), tile_z, tile_x, tile_y)

        if self.has_scale() and scale is not None:
            sql_images += " AND tile_scale=%d " % (scale,)
            sql_map += " AND tile_scale=%d " % (scale,)

        self.cur.execute("DELETE FROM images WHERE tile_id IN (%s)" % (sql_images,))
        self.cur.execute(sql_map)


    def bounding_box_for_zoom_level(self, zoom_level, scale):
        sql = "SELECT min(tile_column), max(tile_column), min(tile_row), max(tile_row) FROM tiles WHERE zoom_level=%d " % (zoom_level,)

        if self.has_scale() and scale is not None:
            sql += " AND tile_scale=%d " % (scale,)

        self.cur.execute(sql)
        return self.cur.fetchone()


    def delete_tile_with_id(self, tile_id):
        self.cur.execute("""DELETE FROM map WHERE tile_id=%s""", (tile_id,));
        self.cur.execute("""DELETE FROM images WHERE tile_id=%s""", (tile_id,))


    def insert_tile_to_images(self, tile_id, tile_data):
        try:
            self.cur.execute("""INSERT INTO images (tile_id, tile_data) VALUES (%s, %s)""",
                (tile_id, psycopg2.Binary(tile_data)))
        except:
            pass


    def insert_tiles_to_images(self, tile_list):
        for t in tile_list:
            self.insert_tile_to_images(t[0], t[1])


    def insert_tile_to_map(self, zoom_level, tile_column, tile_row, tile_scale, tile_id, replace_existing=True):
        if replace_existing:
            if self.has_scale():
                self.cur.execute("""SELECT update_map_proc(%s, %s, %s, %s::smallint, %s::varchar, %s)""",
                    (zoom_level, tile_column, tile_row, tile_scale, tile_id, int(time.time())))
            else:
                self.cur.execute("""SELECT update_map_proc(%s, %s, %s, %s::varchar, %s)""",
                    (zoom_level, tile_column, tile_row, tile_id, int(time.time())))
        else:
            try:
                if self.has_scale():
                    self.cur.execute("""INSERT INTO map (zoom_level, tile_column, tile_row, tile_scale, tile_id, updated_at) VALUES (%s, %s, %s, %s, %s, %s)""",
                        (zoom_level, tile_column, tile_row, tile_scale, tile_id, int(time.time())))
                else:
                    self.cur.execute("""INSERT INTO map (zoom_level, tile_column, tile_row, tile_id, updated_at) VALUES (%s, %s, %s, %s, %s)""",
                        (zoom_level, tile_column, tile_row, tile_id, int(time.time())))
            except:
                pass


    def insert_tiles_to_map(self, tile_list):
        for t in tile_list:
            self.insert_tile_to_map(t[0], t[1], t[2], t[3], t[4])


    def update_tile(self, old_tile_id, new_tile_id, tile_data):
        try:
            self.cur.execute("""INSERT INTO images (tile_id, tile_data) VALUES(%s, %s)""",
                (new_tile_id, psycopg2.Binary(tile_data)))
        except:
            pass

        self.cur.execute("""UPDATE map SET tile_id=%s, updated_at=%s WHERE tile_id=%s""",
            (new_tile_id, int(time.time()), old_tile_id))

        if old_tile_id != new_tile_id:
            self.cur.execute("""DELETE FROM images WHERE tile_id=%s""",
                [old_tile_id])


    def metadata(self):
        try:
            self.cur.execute('SELECT name, value FROM metadata')
            return dict(self.cur.fetchall())
        except Exception, e:
            return None


    def update_metadata(self, key, value):
        try:
            self.cur.execute("""INSERT INTO metadata (name, value) VALUES (%s, %s)""",
                (key, value))
        except:
            self.cur.execute("""UPDATE metadata SET value=%s WHERE name=%s""",
                (value, key))



class MBTilesMySQL(MBTilesDatabase):

    def __init__(self, connect_string, auto_commit=False, journal_mode='wal', synchronous_off=False, exclusive_lock=False, check_if_exists=False):
        try:

            if connect_string.startswith("my:"):
                if os.path.isfile("/etc/mb-util.conf"):
                    config = {}

                    with open("/etc/mb-util.conf") as f:
                        for line in f:
                            try:
                                for (key, value) in (line.strip().split(":", 1),):
                                    config[key.strip()] = value.strip()
                            except:
                                pass

                    key = connect_string.split(':')[1]
                    if len(key):
                        if config.get(key, None) != None:
                            connect_string = config.get(key, connect_string)
                        else:
                            logger.error("Could not find '%s' in /etc/mb-util.conf." % (key))
                            sys.exit(1)

            self.connect_options = dict(option.split("=") for option in connect_string.strip().split(" "))
            self.connect_string = "dbname=%s hostaddr=%s" % (self.connect_options['dbname'], self.connect_options['hostaddr'])

            self.con = oursql.connect(host=self.connect_options['hostaddr'], user=self.connect_options['user'], passwd=self.connect_options['password'], db=self.connect_options['dbname'], raise_on_warnings=False)
            self.cur = self.con.cursor()
            self.cur.execute("SET autocommit = 1")

            if check_if_exists:
                self.cur.execute("SHOW TABLES LIKE 'map'")
                if len(self.cur.fetchall()) == 0:
                    self.close()
                    sys.stderr.write("The mbtiles database and tables must exist for database '%s'.\n" % (self.connect_options['dbname'],))
                    sys.exit(1)

        except Exception, e:
            logger.error("Could not connect to the MySQL database '%s':" % (connect_string))
            logger.error(e)
            sys.exit(1)


    def mbtiles_setup(self):
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS images (
            tile_id CHAR(40),
            tile_data MEDIUMBLOB )""")
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS map (
            zoom_level TINYINT,
            tile_column INTEGER,
            tile_row INTEGER,
            tile_scale TINYINT,
            tile_id CHAR(40),
            updated_at INTEGER )""")
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
            name VARCHAR(200),
            value TEXT )""")

        try:
            self.cur.execute("""
                CREATE UNIQUE INDEX metadata_name_index ON metadata (name)""")
        except:
            pass

        try:
            self.cur.execute("""
                CREATE VIEW tiles AS
                SELECT map.zoom_level AS zoom_level,
                map.tile_column AS tile_column,
                map.tile_row AS tile_row,
                map.tile_scale AS tile_scale,
                images.tile_data AS tile_data,
                map.updated_at AS updated_at
                FROM map
                JOIN images
                ON map.tile_id IS NOT NULL AND images.tile_id = map.tile_id""")
        except Exception, e:
            pass

        try:
            self.cur.execute("""
                CREATE UNIQUE INDEX map_index ON map
                (zoom_level, tile_column, tile_row, tile_scale)""")
        except:
            pass
        try:
            self.cur.execute("""
                CREATE UNIQUE INDEX images_id_index ON images (tile_id)""")
        except:
            pass


    def create_map_tile_index(self):
        self.cur.execute("""CREATE INDEX map_tile_id_index ON map (tile_id)""")


    def drop_map_tile_index(self):
        self.cur.execute("""DROP INDEX map_tile_id_index""")


    def max_timestamp(self):
        self.cur.execute("SELECT max(updated_at) FROM map")
        result = self.cur.fetchall()

        if not result or len(result) == 0:
            return 0

        return result[0]


    def zoom_levels(self, scale):
        sql = "SELECT distinct(zoom_level) FROM tiles "

        if scale is not None:
            sql += " WHERE tile_scale=%d " % (scale,)

        self.cur.execute(sql)
        return [int(x[0]) for x in self.cur.fetchall()]


    def tiles_count(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        sql = "SELECT count(zoom_level) FROM map WHERE "

        if min_zoom > 0:
            sql += " zoom_level>=%d AND " % (min_zoom,)
        if max_zoom < 18:
            sql += " zoom_level<=%d AND " % (max_zoom,)

        if scale is not None:
            sql += " tile_scale=%d AND " % (scale,)

        if min_timestamp > 0:
            sql += " updated_at>%d AND " % (min_timestamp,)
        if max_timestamp > 0:
            sql += " updated_at<%d AND " % (max_timestamp,)

        sql += " tile_id IS NOT NULL"

        logger.debug(sql)

        self.cur.execute(sql)

        result = self.cur.fetchall()
        if len(result) == 0:
            return 0

        return result[0][0]


    def columns_and_rows_for_zoom_level(self, zoom_level, scale):
        tiles_cur = self.con.cursor()
        tiles_cur.execute("SET autocommit = 0")

        tiles_cur.execute("""SELECT tile_column, tile_row FROM map WHERE zoom_level = %s AND tile_scale = %s ORDER BY tile_column, tile_row""",
            [zoom_level, scale])

        t = tiles_cur.fetchone()
        while t:
            yield t
            t = tiles_cur.fetchone()

        tiles_cur.close()


    def columns_for_zoom_level_and_row(self, zoom_level, row, scale):
        self.cur.execute("""SELECT tile_column FROM tiles WHERE zoom_level = %s AND tile_row = %s AND tile_scale = %s""",
            (zoom_level, row, scale))
        return set([int(x[0]) for x in self.cur.fetchall()])


    def tiles_with_tile_id(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        # Second connection to the database, for the named cursor
        iter_con = oursql.connect(host=self.connect_options['hostaddr'], user=self.connect_options['user'], passwd=self.connect_options['password'], db=self.connect_options['dbname'], raise_on_warnings=False)
        tiles_cur = iter_con.cursor()
        tiles_cur.execute("SET autocommit = 0")

        chunk = 10000

        sql = "SELECT map.zoom_level, map.tile_column, map.tile_row, map.tile_scale, images.tile_data, images.tile_id FROM map, images WHERE "

        inner_sql = ""

        if min_zoom > 0:
            inner_sql += " map.zoom_level>=%d " % (min_zoom,)
        if max_zoom < 18:
            if len(inner_sql) > 0:
                inner_sql += " AND "
            inner_sql += " map.zoom_level<=%d " % (max_zoom,)

        if scale is not None:
            if len(inner_sql) > 0:
                inner_sql += " AND "
            inner_sql += " tile_scale=%d " % (scale,)

        if min_timestamp > 0:
            if len(inner_sql) > 0:
                inner_sql += " AND "
            inner_sql += " map.updated_at>%d " % (min_timestamp,)
        if max_timestamp > 0:
            if len(inner_sql) > 0:
                inner_sql += " AND "
            inner_sql += " map.updated_at<%d " % (max_timestamp,)

        if len(inner_sql) > 0:
            sql += " (%s) AND " % (inner_sql,)
        sql += " (map.tile_id IS NOT NULL) AND (images.tile_id = map.tile_id) "

        logger.debug(sql)

        tiles_cur.execute(sql)

        rows = tiles_cur.fetchmany(chunk)
        while rows:
            for t in rows:
                yield t
            rows = tiles_cur.fetchmany(chunk)

        tiles_cur.close()
        iter_con.close()


    def tiles(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        # Second connection to the database, for the named cursor
        iter_con = oursql.connect(host=self.connect_options['hostaddr'], user=self.connect_options['user'], passwd=self.connect_options['password'], db=self.connect_options['dbname'], raise_on_warnings=False)
        tiles_cur = iter_con.cursor()
        tiles_cur.execute("SET autocommit = 0")

        chunk = 10000

        sql = "SELECT zoom_level, tile_column, tile_row, tile_scale, tile_data FROM tiles WHERE "

        if min_zoom > 0:
            sql += " zoom_level>=%d AND " % (min_zoom,)
        if max_zoom < 18:
            sql += " zoom_level<=%d AND " % (max_zoom,)

        if scale is not None:
            sql += " tile_scale=%d AND " % (scale,)

        if min_timestamp > 0:
            sql += " updated_at>%d AND " % (min_timestamp,)
        if max_timestamp > 0:
            sql += " updated_at<%d AND " % (max_timestamp,)

        sql += " 1 "

        logger.debug(sql)

        tiles_cur.execute(sql)

        rows = tiles_cur.fetchmany(chunk)
        while rows:
            for t in rows:
                yield t
            rows = tiles_cur.fetchmany(chunk)

        tiles_cur.close()
        iter_con.close()


    def updates(self, min_zoom, max_zoom, min_timestamp, max_timestamp):
        tiles_cur = self.con.cursor()
        tiles_cur.execute("SET autocommit = 0")

        chunk = 10000

        tiles_cur.execute("""
            SELECT map.zoom_level, map.tile_column, map.tile_row, map.tile_scale, images.tile_data, images.tile_id
            FROM map, images
            WHERE (map.zoom_level>=? and map.zoom_level<=? AND map.updated_at>? AND map.updated_at<?) AND (images.tile_id == map.tile_id)
            UNION
            SELECT map.zoom_level, map.tile_column, map.tile_row, map.tile_scale, NULL, NULL
            FROM map
            WHERE (map.zoom_level>=? and map.zoom_level<=? AND map.updated_at>? AND map.updated_at<?) AND (map.tile_id IS NULL)
            """,
            (min_zoom, max_zoom, min_timestamp, max_timestamp, min_zoom, max_zoom, min_timestamp, max_timestamp))

        rows = tiles_cur.fetchmany(chunk)
        while rows:
            for t in rows:
                yield t
            rows = tiles_cur.fetchmany(chunk)

        tiles_cur.close()


    def updates_count(self, min_zoom, max_zoom, min_timestamp, max_timestamp):
        total_tiles = self.cur.execute("""SELECT count(zoom_level) FROM map WHERE zoom_level>=? AND zoom_level<=? AND updated_at>? AND updated_at<?""",
            (min_zoom, max_zoom, min_timestamp, max_timestamp)).fetchall()[0][0]

        return total_tiles


    def delete_tiles(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        sql_images = "SELECT tile_id FROM map WHERE zoom_level>=%d AND zoom_level<=%d " % (min_zoom, max_zoom)
        sql_map = "DELETE FROM map WHERE zoom_level>=%d AND zoom_level<=%d " % (min_zoom, max_zoom)

        if scale is not None:
            sql_images += " AND tile_scale=%d " % (scale,)
            sql_map += " AND tile_scale=%d " % (scale,)

        if min_timestamp > 0:
            sql_images += " AND updated_at>%d " % (min_timestamp,)
            sql_map += " AND updated_at>%d " % (min_timestamp,)
        if max_timestamp > 0:
            sql_images += " AND updated_at<%d " (max_timestamp,)
            sql_map += " AND updated_at<%d " % (max_timestamp,)

        self.cur.execute("DELETE FROM images WHERE tile_id IN (%s)" % (sql_images,))
        self.cur.execute(sql_map)


        sql_images = "SELECT tile_id FROM map WHERE zoom_level>=%d AND zoom_level<=%d " % (min_zoom, max_zoom)
        sql_map = "UPDATE map SET tile_id=NULL, updated_at=%d WHERE zoom_level>=%d AND zoom_level<=%d " % (int(time.time()), min_zoom, max_zoom)

        if scale is not None:
            sql_images += " AND tile_scale=%d " % (scale,)
            sql_map += " AND tile_scale=%d " % (scale,)

        if min_timestamp > 0:
            sql_images += " AND updated_at>%d " % (min_timestamp,)
            sql_map += " AND updated_at>%d " % (min_timestamp,)
        if max_timestamp > 0:
            sql_images += " AND updated_at<%d " % (max_timestamp,)
            sql_map += " AND updated_at<%d " % (max_timestamp,)

        self.cur.execute("DELETE FROM images WHERE tile_id IN (%s)" % (sql_images,))
        self.cur.execute(sql_map)


    def expire_tile(self, tile_z, tile_x, tile_y, scale):
        sql_images = "SELECT tile_id FROM map WHERE zoom_level=%d AND tile_column=%d AND tile_row=%d " % (tile_z, tile_x, tile_y)
        sql_map = "UPDATE map SET tile_id=NULL, updated_at=%d WHERE zoom_level=%d AND tile_column=%d AND tile_row=%d " % (int(time.time()), tile_z, tile_x, tile_y)

        if scale is not None:
            sql_images += " AND tile_scale=%d " % (scale,)
            sql_map += " AND tile_scale=%d " % (scale,)

        self.cur.execute("DELETE FROM images WHERE tile_id IN (%s)" % (sql_images,))
        self.cur.execute(sql_map)


    def bounding_box_for_zoom_level(self, zoom_level, scale):
        sql = "SELECT min(tile_column), max(tile_column), min(tile_row), max(tile_row) FROM tiles WHERE zoom_level=%d " % (zoom_level,)

        if scale is not None:
            sql += " AND tile_scale=%d " % (scale,)

        self.cur.execute(sql)
        return self.cur.fetchall()[0]


    def delete_tile_with_id(self, tile_id):
        self.cur.execute("""DELETE FROM map WHERE tile_id=?""", (tile_id, ));
        self.cur.execute("""DELETE FROM images WHERE tile_id=?""", (tile_id, ))


    def insert_tile_to_images(self, tile_id, tile_data):
        self.cur.execute("""INSERT IGNORE INTO images (tile_id, tile_data) VALUES (?, ?)""",
            (tile_id, buffer(tile_data)))


    def insert_tiles_to_images(self, tile_list):
        self.cur.executemany("""INSERT IGNORE INTO images (tile_id, tile_data) VALUES (?, ?)""", [(t[0], buffer(t[1])) for t in tile_list])


    def insert_tile_to_map(self, zoom_level, tile_column, tile_row, tile_scale, tile_id, replace_existing=True):
        if replace_existing:
            self.cur.execute("""REPLACE INTO map (zoom_level, tile_column, tile_row, tile_scale, tile_id, updated_at) VALUES (?, ?, ?, ?, ?, ?)""",
                (zoom_level, tile_column, tile_row, tile_scale, tile_id, int(time.time())))
        else:
            self.cur.execute("""INSERT IGNORE INTO map (zoom_level, tile_column, tile_row, tile_scale, tile_id, updated_at) VALUES (?, ?, ?, ?, ?, ?)""",
                (zoom_level, tile_column, tile_row, tile_scale, tile_id, int(time.time())))


    def insert_tiles_to_map(self, tile_list):
        self.cur.executemany("""REPLACE INTO map (zoom_level, tile_column, tile_row, tile_scale, tile_id, updated_at) VALUES (?, ?, ?, ?, ?, ?)""", tile_list)


    def update_tile(self, old_tile_id, new_tile_id, tile_data):
        self.cur.execute("""INSERT OR IGNORE INTO images (tile_id, tile_data) VALUES (?, ?)""",
            (new_tile_id, sqlite3.Binary(tile_data)))
        self.cur.execute("""UPDATE map SET tile_id=?, updated_at=? WHERE tile_id=?""",
            (new_tile_id, int(time.time()), old_tile_id))

        if old_tile_id != new_tile_id:
            self.cur.execute("""DELETE FROM images WHERE tile_id=?""",
                [old_tile_id])


    def metadata(self):
        try:
            self.cur.execute('SELECT name, value FROM metadata')
            return dict(self.cur.fetchall())
        except Exception, e:
            return None


    def update_metadata(self, key, value):
        self.cur.execute('REPLACE INTO metadata (name, value) VALUES (?, ?)',
            (key, value))


class MBTilesMongoDB(MBTilesDatabase):

    def __init__(self, connect_string, auto_commit=False, journal_mode='wal', synchronous_off=False, exclusive_lock=False, check_if_exists=False):
        try:

            if connect_string.startswith("mongodb:"):
                if os.path.isfile("/etc/mb-util.conf"):
                    config = {}

                    with open("/etc/mb-util.conf") as f:
                        for line in f:
                            try:
                                for (key, value) in (line.strip().split(":", 1),):
                                    config[key.strip()] = value.strip()
                            except:
                                pass

                    key = connect_string.split(':')[1]
                    if len(key):
                        if config.get(key, None) != None:
                            connect_string = config.get(key, connect_string)
                        else:
                            logger.error("Could not find '%s' in /etc/mb-util.conf." % (key))
                            sys.exit(1)

            self.connect_options = dict(option.split("=") for option in connect_string.strip().split(" "))
            self.connect_string = "mongodb://%s:%s@%s/admin" % (self.connect_options['user'], self.connect_options['password'], self.connect_options.get('hostaddr', self.connect_options.get('host', '127.0.0.1')))

            self.con = pymongo.mongo_client.MongoClient(self.connect_string)
            self.cur = self.con[self.connect_options['dbname']]

        except Exception, e:
            logger.error("Could not connect to the MongoDB database '%s':" % (connect_string))
            logger.error(e)
            sys.exit(1)

    def close(self):
        self.con.close()

    def is_compacted(self):
        return False

    def mbtiles_setup(self):
        pass

    def optimize_database(self, skip_analyze, skip_vacuum):
        pass

    def create_map_tile_index(self):
        pass

    def drop_map_tile_index(self):
        pass

    def max_timestamp(self):
        return 0

    def zoom_levels(self, scale):
        return self.cur.tiles.distinct("z")

    def tiles_count(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        query = {}

        if min_zoom > 0 or max_zoom < 18:
            z_query = {}
            if min_zoom > 0:
                z_query["$gte"] = min_zoom
            if max_zoom < 18:
                z_query["$lte"] = max_zoom
            query["z"] = z_query

        if scale is not None:
            query["s"] = scale

        if min_timestamp > 0 or max_timestamp > 0:
            t_query = {}
            if min_timestamp > 0:
                t_query["$gt"] = min_timestamp
            if max_timestamp > 0:
                t_query["$lt"] = max_timestamp
            query["t"] = t_query

        if len(query):
            return self.cur.tiles.find(query).count()

        return self.cur.tiles.count()

    def columns_and_rows_for_zoom_level(self, zoom_level, scale):
        raise("Not implemented")

    def columns_for_zoom_level_and_row(self, zoom_level, row, scale):
        raise("Not implemented")

    def tiles_with_tile_id(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        return tiles(min_zoom, max_zoom, min_timestamp, max_timestamp, scale)

    def tiles(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        query = {}

        if min_zoom > 0 or max_zoom < 18:
            z_query = {}
            if min_zoom > 0:
                z_query["$gte"] = min_zoom
            if max_zoom < 18:
                z_query["$lte"] = max_zoom
            query["z"] = z_query

        if scale is not None:
            query["s"] = scale

        if min_timestamp > 0 or max_timestamp > 0:
            t_query = {}
            if min_timestamp > 0:
                t_query["$gt"] = min_timestamp
            if max_timestamp > 0:
                t_query["$lt"] = max_timestamp
            query["t"] = t_query

        cur = self.cur.tiles.find(query)

        for t in cur:
            tile_id = t["_id"]
            tile_z, tile_x, tile_y, tile_scale = tile_id.split('/')

            yield [ int(tile_z), int(tile_x), int(tile_y), int(tile_scale), t["d"]]

    def updates(self, min_zoom, max_zoom, min_timestamp, max_timestamp):
        raise("Not implemented")

    def updates_count(self, min_zoom, max_zoom, min_timestamp, max_timestamp):
        raise("Not implemented")

    def delete_tiles(self, min_zoom, max_zoom, min_timestamp, max_timestamp, scale):
        raise("Not implemented")

    def expire_tile(self, tile_z, tile_x, tile_y, tile_scale):
        tile_id = "%s/%s/%s/%s" % (tile_z, tile_x, tile_y, tile_scale)
        self.cur.tiles.remove({ "_id" : tile_id })

    def bounding_box_for_zoom_level(self, zoom_level, scale):
        raise("Not implemented")

    def delete_tile_with_id(self, tile_id):
        raise("Not implemented")

    def insert_tile(self, zoom_level, tile_column, tile_row, tile_scale, tile_data):
        raise Exception("Not implemented.")

    # tile_list must be an array of (z, x, y, scale, tile_data, timestamp)
    def insert_tiles(self, tile_list):
        bulk = self.cur.tiles.initialize_ordered_bulk_op()

        for t in tile_list:
            tile_z = t[0]
            tile_x = t[1]
            tile_y = t[2]
            tile_scale = t[3]
            tile_data = bson.binary.Binary(t[4])
            timestamp = t[5]

            tile_id = "%s/%s/%s/%s" % (tile_z, tile_x, tile_y, tile_scale)

            bulk.find({ "_id" : tile_id }).upsert().update( { "$set" : {"_id" : tile_id, "z" : tile_z, "t" : timestamp, "d" : tile_data}})

        return bulk.execute()

    def metadata(self):
        try:
            metadata = {}

            for t in self.cur.metadata.find():
                metadata[t["name"]] = t["value"]

            return metadata
        except Exception, e:
            return None

    def update_metadata(self, key, value):
        self.cur.metadata.update({"name" : key}, {"name" : key, "value" : value}, True)
