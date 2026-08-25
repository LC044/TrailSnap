"""Create the frozen initial TrailSnap SQLite schema.

This revision intentionally contains a static schema snapshot. Never import
application metadata here: later model changes must be represented by a new
SQLite revision so fresh installs and existing databases follow the same chain.
"""

from alembic import op
import sqlalchemy as sa


revision = "sqlite_0001"
down_revision = None
branch_labels = None
depends_on = None


TABLE_DDL = ('CREATE TABLE image_clusters (\n'
 '\tcluster_id CHAR(36) NOT NULL, \n'
 '\ttask_id VARCHAR(255), \n'
 '\tcluster_type VARCHAR(50) NOT NULL, \n'
 '\tcount INTEGER, \n'
 '\tcreated_at DATETIME, \n'
 '\tPRIMARY KEY (cluster_id)\n'
 ')',
 'CREATE TABLE system_state (\n'
 '\t"key" VARCHAR NOT NULL, \n'
 '\tvalue TEXT, \n'
 '\tPRIMARY KEY ("key")\n'
 ')',
 'CREATE TABLE users (\n'
 '\tid CHAR(36) NOT NULL, \n'
 '\tusername VARCHAR, \n'
 '\temail VARCHAR, \n'
 '\tnickname VARCHAR, \n'
 '\tavatar VARCHAR, \n'
 '\thashed_password VARCHAR, \n'
 '\tis_active BOOLEAN, \n'
 '\tis_superuser BOOLEAN, \n'
 '\tfailed_login_attempts INTEGER, \n'
 '\tlast_failed_login DATETIME, \n'
 '\tlockout_until DATETIME, \n'
 '\tsecurity_question VARCHAR, \n'
 '\tsecurity_answer_hash VARCHAR, \n'
 '\tsettings JSON, \n'
 '\tPRIMARY KEY (id)\n'
 ')',
 'CREATE TABLE agent_sessions (\n'
 '\tid CHAR(36) NOT NULL, \n'
 '\tuser_id CHAR(36) NOT NULL, \n'
 '\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP, \n'
 '\ttitle VARCHAR(255), \n'
 '\tstatus VARCHAR(50), \n'
 '\tcontext_summary TEXT, \n'
 '\tsummary_update_time DATETIME, \n'
 '\tis_pinned BOOLEAN, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE agent_tokens (\n'
 '\tid CHAR(36) NOT NULL, \n'
 '\tuser_id CHAR(36) NOT NULL, \n'
 '\tname VARCHAR NOT NULL, \n'
 '\ttoken VARCHAR NOT NULL, \n'
 '\tcreated_at DATETIME NOT NULL, \n'
 '\texpires_at DATETIME NOT NULL, \n'
 '\tis_deleted BOOLEAN NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE face_identities (\n'
 '\tid CHAR(36) NOT NULL, \n'
 '\tidentity_name VARCHAR(500), \n'
 '\tdescription VARCHAR(500), \n'
 '\ttags JSON, \n'
 '\tdefault_face_id INTEGER, \n'
 '\tcreate_time DATETIME, \n'
 '\tupdate_time DATETIME, \n'
 '\tis_deleted BOOLEAN, \n'
 '\tis_hidden BOOLEAN, \n'
 '\towner_id CHAR(36), \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(default_face_id) REFERENCES faces (id) ON DELETE SET NULL, \n'
 '\tFOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE index_logs (\n'
 '\tid INTEGER NOT NULL, \n'
 '\taction VARCHAR(50) NOT NULL, \n'
 '\tfile_path TEXT NOT NULL, \n'
 '\tphoto_id CHAR(36), \n'
 '\tdetails TEXT, \n'
 '\towner_id CHAR(36), \n'
 '\tcreated_at DATETIME, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE moment_day_captions (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tuser_id CHAR(36) NOT NULL, \n'
 "\tscope_type VARCHAR(16) DEFAULT 'all' NOT NULL, \n"
 '\tscope_id VARCHAR(64), \n'
 '\tday DATE NOT NULL, \n'
 '\tcaption TEXT NOT NULL, \n'
 "\tsource VARCHAR(16) DEFAULT 'ai' NOT NULL, \n"
 '\tmodel_name VARCHAR(64), \n'
 "\tphoto_count INTEGER DEFAULT '0' NOT NULL, \n"
 "\tcomment_count INTEGER DEFAULT '0' NOT NULL, \n"
 '\tlast_commented_at DATETIME, \n'
 '\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, \n'
 '\tupdated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_moment_day_caption_user_scope_day UNIQUE (user_id, scope_type, scope_id, day), \n'
 '\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE notifications (\n'
 '\tid CHAR(36) NOT NULL, \n'
 '\tuser_id CHAR(36) NOT NULL, \n'
 '\ttype VARCHAR(32) NOT NULL, \n'
 '\tlevel VARCHAR(16) NOT NULL, \n'
 '\ttitle VARCHAR(255) NOT NULL, \n'
 '\tbody JSON, \n'
 '\tref_type VARCHAR(32), \n'
 '\tref_id VARCHAR(64), \n'
 '\tread BOOLEAN DEFAULT false NOT NULL, \n'
 '\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL, \n'
 '\tread_at DATETIME, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE photos (\n'
 '\tid CHAR(36) NOT NULL, \n'
 '\tfilename VARCHAR(255), \n'
 '\tphoto_time DATETIME, \n'
 '\tfile_path VARCHAR(255) NOT NULL, \n'
 '\tfile_type VARCHAR(10) NOT NULL, \n'
 '\tupload_time DATETIME, \n'
 '\tsize BIGINT, \n'
 '\twidth INTEGER, \n'
 '\theight INTEGER, \n'
 '\tduration FLOAT, \n'
 '\timage_type VARCHAR(10), \n'
 '\tmd5 VARCHAR(32), \n'
 '\tprocessed_tasks JSON, \n'
 '\towner_id CHAR(36), \n'
 '\tis_deleted BOOLEAN NOT NULL, \n'
 '\tdeleted_at DATETIME, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(owner_id) REFERENCES users (id)\n'
 ')',
 'CREATE TABLE scenes (\n'
 '\tid CHAR(36) NOT NULL, \n'
 '\tname VARCHAR(255) NOT NULL, \n'
 '\tdescription TEXT, \n'
 '\tlevel INTEGER, \n'
 '\taddress TEXT, \n'
 '\tlatitude DECIMAL(10, 7), \n'
 '\tlongitude DECIMAL(10, 7), \n'
 '\tradius INTEGER, \n'
 '\tpolygon JSON, \n'
 '\tis_custom BOOLEAN, \n'
 '\towner_id CHAR(36), \n'
 '\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE tasks (\n'
 '\tid CHAR(36) NOT NULL, \n'
 '\ttype VARCHAR(50) NOT NULL, \n'
 '\tstatus VARCHAR(20), \n'
 '\tpriority INTEGER, \n'
 '\tpayload JSON, \n'
 '\tresult JSON, \n'
 '\terror TEXT, \n'
 '\towner_id CHAR(36), \n'
 '\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP, \n'
 '\tupdated_at DATETIME DEFAULT CURRENT_TIMESTAMP, \n'
 '\ttotal_items INTEGER, \n'
 '\tprocessed_items INTEGER, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE agent_messages (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tsession_id CHAR(36) NOT NULL, \n'
 '\trole VARCHAR(50) NOT NULL, \n'
 '\tcontent TEXT NOT NULL, \n'
 '\tcontent_type VARCHAR(50), \n'
 '\tcontent_ext JSON, \n'
 '\treasoning TEXT, \n'
 '\ttool_calls JSON, \n'
 '\ttoken_count INTEGER, \n'
 '\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(session_id) REFERENCES agent_sessions (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE albums (\n'
 '\tid CHAR(36) NOT NULL, \n'
 '\tname VARCHAR(100) NOT NULL, \n'
 '\tcreate_time DATETIME, \n'
 '\tdescription TEXT, \n'
 '\tcover CHAR(36), \n'
 '\ttype VARCHAR(20) NOT NULL, \n'
 '\tcondition JSON, \n'
 '\tquery_embedding JSON, \n'
 '\tnum_photos INTEGER, \n'
 '\tthreshold FLOAT, \n'
 '\towner_id CHAR(36), \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(cover) REFERENCES photos (id) ON DELETE SET NULL, \n'
 '\tFOREIGN KEY(owner_id) REFERENCES users (id)\n'
 ')',
 'CREATE TABLE faces (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tphoto_id CHAR(36) NOT NULL, \n'
 '\tface_identity_id CHAR(36), \n'
 '\tface_feature JSON, \n'
 '\tface_rect JSON, \n'
 '\tface_confidence DECIMAL(5, 4), \n'
 '\trecognize_confidence DECIMAL(5, 4), \n'
 '\tcreate_time DATETIME, \n'
 '\tupdate_time DATETIME, \n'
 '\tis_deleted BOOLEAN, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(photo_id) REFERENCES photos (id) ON DELETE CASCADE, \n'
 '\tFOREIGN KEY(face_identity_id) REFERENCES face_identities (id) ON DELETE SET NULL\n'
 ')',
 'CREATE TABLE flight_tickets (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\tflight_code VARCHAR(20) NOT NULL, \n'
 '\tdeparture_city VARCHAR(50) NOT NULL, \n'
 '\tarrival_city VARCHAR(50) NOT NULL, \n'
 '\tdate_time DATETIME NOT NULL, \n'
 '\tprice NUMERIC(10, 2) NOT NULL, \n'
 '\tname VARCHAR(50) NOT NULL, \n'
 '\ttotal_mileage DECIMAL(10, 1) NOT NULL, \n'
 '\ttotal_running_time INTEGER NOT NULL, \n'
 '\tcomments TEXT, \n'
 '\tcreated_at DATETIME, \n'
 '\tupdated_at DATETIME, \n'
 '\tphoto_id CHAR(36), \n'
 '\towner_id CHAR(36), \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(photo_id) REFERENCES photos (id) ON DELETE SET NULL, \n'
 '\tFOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE image_descriptions (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tphoto_id CHAR(36) NOT NULL, \n'
 '\tdescription TEXT, \n'
 '\tmemory_score FLOAT, \n'
 '\tquality_score FLOAT, \n'
 '\ttags JSON, \n'
 '\treason TEXT, \n'
 '\tnarrative TEXT, \n'
 '\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(photo_id) REFERENCES photos (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE image_vectors (\n'
 '\tphoto_id CHAR(36) NOT NULL, \n'
 '\tembedding JSON, \n'
 '\tcreated_at DATETIME, \n'
 '\tmodel_name VARCHAR, \n'
 '\tPRIMARY KEY (photo_id), \n'
 '\tFOREIGN KEY(photo_id) REFERENCES photos (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE ocr_results (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tphoto_id CHAR(36) NOT NULL, \n'
 '\ttext VARCHAR, \n'
 '\ttext_score FLOAT, \n'
 '\tpolygon JSON, \n'
 '\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP, \n'
 '\tupdated_at DATETIME DEFAULT CURRENT_TIMESTAMP, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(photo_id) REFERENCES photos (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE photo_clusters (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tphoto_id CHAR(36) NOT NULL, \n'
 '\tcluster_id CHAR(36) NOT NULL, \n'
 '\tcreated_at DATETIME, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(photo_id) REFERENCES photos (id) ON DELETE CASCADE, \n'
 '\tFOREIGN KEY(cluster_id) REFERENCES image_clusters (cluster_id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE photo_colors (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tphoto_id CHAR(36) NOT NULL, \n'
 '\tdominant_colors JSON, \n'
 '\tbrightness FLOAT, \n'
 '\tsaturation FLOAT, \n'
 '\temotion_hint VARCHAR(20), \n'
 '\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(photo_id) REFERENCES photos (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE photo_metadata (\n'
 '\tphoto_id CHAR(36) NOT NULL, \n'
 '\texif_info TEXT, \n'
 '\tlongitude DECIMAL(10, 7), \n'
 '\tlatitude DECIMAL(10, 7), \n'
 '\tcity VARCHAR(100), \n'
 '\tdistrict VARCHAR(100), \n'
 '\tprovince VARCHAR(100), \n'
 '\tcountry VARCHAR(100), \n'
 '\taddress TEXT, \n'
 '\tmake VARCHAR(100), \n'
 '\tmodel VARCHAR(100), \n'
 '\tshooting_params JSON, \n'
 '\tlocation_api VARCHAR(255), \n'
 '\tscene_id CHAR(36), \n'
 '\tPRIMARY KEY (photo_id), \n'
 '\tFOREIGN KEY(photo_id) REFERENCES photos (id) ON DELETE CASCADE, \n'
 '\tFOREIGN KEY(scene_id) REFERENCES scenes (id) ON DELETE SET NULL\n'
 ')',
 'CREATE TABLE photo_tags (\n'
 '\tid CHAR(36) NOT NULL, \n'
 '\ttag_name VARCHAR(50) NOT NULL, \n'
 '\ttype VARCHAR(50), \n'
 '\tcover_id CHAR(36), \n'
 '\towner_id CHAR(36), \n'
 '\tcreate_time DATETIME, \n'
 '\tupdate_time DATETIME, \n'
 '\tis_deleted BOOLEAN, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(cover_id) REFERENCES photos (id) ON DELETE SET NULL, \n'
 '\tFOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE train_tickets (\n'
 '\tid VARCHAR(36) NOT NULL, \n'
 '\ttrain_code VARCHAR(20) NOT NULL, \n'
 '\tdeparture_station VARCHAR(50) NOT NULL, \n'
 '\tarrival_station VARCHAR(50) NOT NULL, \n'
 '\tdate_time DATETIME NOT NULL, \n'
 '\tcarriage VARCHAR(10) NOT NULL, \n'
 '\tseat_num VARCHAR(10) NOT NULL, \n'
 '\tberth_type VARCHAR(10), \n'
 '\tprice NUMERIC(10, 2) NOT NULL, \n'
 '\tseat_type VARCHAR(20) NOT NULL, \n'
 '\tname VARCHAR(50) NOT NULL, \n'
 '\tdiscount_type VARCHAR(20), \n'
 '\ttotal_mileage DECIMAL(10, 1) NOT NULL, \n'
 '\ttotal_running_time INTEGER NOT NULL, \n'
 '\tstop_stations TEXT, \n'
 '\tcomments TEXT, \n'
 '\tcreated_at DATETIME, \n'
 '\tupdated_at DATETIME, \n'
 '\tphoto_id CHAR(36), \n'
 '\towner_id CHAR(36), \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(photo_id) REFERENCES photos (id) ON DELETE SET NULL, \n'
 '\tFOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE album_photos (\n'
 '\tid INTEGER NOT NULL, \n'
 '\talbum_id CHAR(36) NOT NULL, \n'
 '\tphoto_id CHAR(36) NOT NULL, \n'
 '\tcreated_at DATETIME, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_album_photo UNIQUE (album_id, photo_id), \n'
 '\tFOREIGN KEY(album_id) REFERENCES albums (id) ON DELETE CASCADE, \n'
 '\tFOREIGN KEY(photo_id) REFERENCES photos (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE album_shared_users (\n'
 '\talbum_id CHAR(36) NOT NULL, \n'
 '\tuser_id CHAR(36) NOT NULL, \n'
 '\tcreated_at DATETIME, \n'
 '\tPRIMARY KEY (album_id, user_id), \n'
 '\tFOREIGN KEY(album_id) REFERENCES albums (id) ON DELETE CASCADE, \n'
 '\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n'
 ')',
 'CREATE TABLE photo_tag_relations (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tphoto_id CHAR(36) NOT NULL, \n'
 '\ttag_id CHAR(36) NOT NULL, \n'
 '\tconfidence FLOAT, \n'
 '\tcreated_at DATETIME, \n'
 '\tis_deleted BOOLEAN, \n'
 '\tPRIMARY KEY (id), \n'
 '\tCONSTRAINT uq_photo_tag UNIQUE (photo_id, tag_id), \n'
 '\tFOREIGN KEY(photo_id) REFERENCES photos (id) ON DELETE CASCADE, \n'
 '\tFOREIGN KEY(tag_id) REFERENCES photo_tags (id) ON DELETE CASCADE\n'
 ')')

INDEX_DDL = ('CREATE INDEX ix_system_state_key ON system_state ("key")',
 'CREATE UNIQUE INDEX ix_users_email ON users (email)',
 'CREATE INDEX ix_users_id ON users (id)',
 'CREATE UNIQUE INDEX ix_users_username ON users (username)',
 'CREATE INDEX ix_agent_sessions_id ON agent_sessions (id)',
 'CREATE INDEX ix_agent_sessions_user_id ON agent_sessions (user_id)',
 'CREATE INDEX ix_agent_tokens_id ON agent_tokens (id)',
 'CREATE UNIQUE INDEX ix_agent_tokens_token ON agent_tokens (token)',
 'CREATE INDEX ix_agent_tokens_user_id ON agent_tokens (user_id)',
 'CREATE INDEX ix_face_identities_identity_name ON face_identities (identity_name)',
 'CREATE INDEX ix_face_identities_owner_id ON face_identities (owner_id)',
 'CREATE INDEX ix_index_logs_owner_id ON index_logs (owner_id)',
 'CREATE INDEX ix_moment_day_captions_day ON moment_day_captions (day)',
 'CREATE INDEX ix_moment_day_captions_id ON moment_day_captions (id)',
 'CREATE INDEX ix_moment_day_captions_user_id ON moment_day_captions (user_id)',
 'CREATE INDEX ix_notif_user_created ON notifications (user_id, created_at)',
 'CREATE INDEX ix_notif_user_read ON notifications (user_id, read)',
 'CREATE INDEX ix_notifications_id ON notifications (id)',
 'CREATE INDEX ix_notifications_read ON notifications (read)',
 'CREATE INDEX ix_notifications_user_id ON notifications (user_id)',
 'CREATE INDEX ix_photos_deleted_at ON photos (deleted_at)',
 'CREATE INDEX ix_photos_file_path ON photos (file_path)',
 'CREATE INDEX ix_photos_filename ON photos (filename)',
 'CREATE INDEX ix_photos_is_deleted ON photos (is_deleted)',
 'CREATE INDEX ix_photos_md5 ON photos (md5)',
 'CREATE INDEX ix_photos_owner_id ON photos (owner_id)',
 'CREATE INDEX ix_photos_photo_time ON photos (photo_time)',
 'CREATE INDEX ix_scenes_name ON scenes (name)',
 'CREATE INDEX ix_scenes_owner_id ON scenes (owner_id)',
 'CREATE INDEX ix_tasks_owner_id ON tasks (owner_id)',
 'CREATE INDEX ix_tasks_status_priority_created ON tasks (status, priority, created_at)',
 'CREATE INDEX ix_tasks_type_status ON tasks (type, status)',
 'CREATE INDEX ix_agent_messages_session_id ON agent_messages (session_id)',
 'CREATE INDEX ix_albums_name ON albums (name)',
 'CREATE INDEX ix_albums_owner_id ON albums (owner_id)',
 'CREATE INDEX idx_face_feature ON faces (face_feature)',
 'CREATE INDEX idx_face_identity_id ON faces (face_identity_id)',
 'CREATE INDEX idx_face_photo_id ON faces (photo_id)',
 'CREATE INDEX ix_flight_tickets_flight_code ON flight_tickets (flight_code)',
 'CREATE INDEX ix_flight_tickets_id ON flight_tickets (id)',
 'CREATE INDEX ix_flight_tickets_owner_id ON flight_tickets (owner_id)',
 'CREATE INDEX ix_flight_tickets_photo_id ON flight_tickets (photo_id)',
 'CREATE INDEX ix_image_descriptions_id ON image_descriptions (id)',
 'CREATE INDEX ix_image_descriptions_photo_id ON image_descriptions (photo_id)',
 'CREATE INDEX ix_ocr_results_photo_id ON ocr_results (photo_id)',
 'CREATE INDEX ix_ocr_results_text ON ocr_results (text)',
 'CREATE INDEX ix_photo_colors_id ON photo_colors (id)',
 'CREATE UNIQUE INDEX ix_photo_colors_photo_id ON photo_colors (photo_id)',
 'CREATE INDEX idx_location_city ON photo_metadata (city)',
 'CREATE INDEX idx_location_country ON photo_metadata (country)',
 'CREATE INDEX idx_location_lat_lng ON photo_metadata (latitude, longitude)',
 'CREATE INDEX idx_location_province ON photo_metadata (province)',
 'CREATE INDEX ix_photo_metadata_address ON photo_metadata (address)',
 'CREATE INDEX ix_photo_metadata_city ON photo_metadata (city)',
 'CREATE INDEX ix_photo_metadata_country ON photo_metadata (country)',
 'CREATE INDEX ix_photo_metadata_district ON photo_metadata (district)',
 'CREATE INDEX ix_photo_metadata_province ON photo_metadata (province)',
 'CREATE INDEX ix_photo_tags_owner_id ON photo_tags (owner_id)',
 'CREATE INDEX ix_photo_tags_tag_name ON photo_tags (tag_name)',
 'CREATE INDEX ix_train_tickets_id ON train_tickets (id)',
 'CREATE INDEX ix_train_tickets_owner_id ON train_tickets (owner_id)',
 'CREATE INDEX ix_train_tickets_photo_id ON train_tickets (photo_id)',
 'CREATE INDEX ix_train_tickets_train_code ON train_tickets (train_code)')

TABLE_NAMES = ('image_clusters',
 'system_state',
 'users',
 'agent_sessions',
 'agent_tokens',
 'face_identities',
 'index_logs',
 'moment_day_captions',
 'notifications',
 'photos',
 'scenes',
 'tasks',
 'agent_messages',
 'albums',
 'faces',
 'flight_tickets',
 'image_descriptions',
 'image_vectors',
 'ocr_results',
 'photo_clusters',
 'photo_colors',
 'photo_metadata',
 'photo_tags',
 'train_tickets',
 'album_photos',
 'album_shared_users',
 'photo_tag_relations')


def upgrade() -> None:
    for statement in TABLE_DDL + INDEX_DDL:
        op.execute(sa.text(statement))


def downgrade() -> None:
    for table_name in reversed(TABLE_NAMES):
        op.drop_table(table_name)
