CREATE TEMP TABLE local_repair_map_revision(singleton INTEGER PRIMARY KEY CHECK(singleton=1),revision INTEGER NOT NULL);
INSERT INTO local_repair_map_revision VALUES(1,0);
CREATE TEMP TABLE local_repair_map_journal(revision INTEGER NOT NULL,image INTEGER NOT NULL);
CREATE INDEX temp.local_repair_map_journal_revision ON local_repair_map_journal(revision,image);
CREATE TEMP TRIGGER local_repair_map_insert AFTER INSERT ON main.AgLibraryImageOzAssetIds BEGIN
 UPDATE local_repair_map_revision SET revision=revision+1;
 INSERT INTO local_repair_map_journal SELECT revision,NEW.image FROM local_repair_map_revision;
END;
CREATE TEMP TRIGGER local_repair_map_delete AFTER DELETE ON main.AgLibraryImageOzAssetIds BEGIN
 UPDATE local_repair_map_revision SET revision=revision+1;
 INSERT INTO local_repair_map_journal SELECT revision,OLD.image FROM local_repair_map_revision;
END;
CREATE TEMP TRIGGER local_repair_map_update AFTER UPDATE OF image,ozCatalogId,ozAssetId ON main.AgLibraryImageOzAssetIds
 WHEN OLD.image IS NOT NEW.image OR OLD.ozCatalogId IS NOT NEW.ozCatalogId OR OLD.ozAssetId IS NOT NEW.ozAssetId BEGIN
 UPDATE local_repair_map_revision SET revision=revision+1;
 INSERT INTO local_repair_map_journal SELECT revision,OLD.image FROM local_repair_map_revision;
 INSERT INTO local_repair_map_journal SELECT revision,NEW.image FROM local_repair_map_revision;
END;
CREATE TEMP TRIGGER local_repair_photo_insert AFTER INSERT ON main.Adobe_images BEGIN
 UPDATE local_repair_map_revision SET revision=revision+1;
 INSERT INTO local_repair_map_journal SELECT revision,NEW.id_local FROM local_repair_map_revision;
END;
CREATE TEMP TRIGGER local_repair_photo_delete AFTER DELETE ON main.Adobe_images BEGIN
 UPDATE local_repair_map_revision SET revision=revision+1;
 INSERT INTO local_repair_map_journal SELECT revision,OLD.id_local FROM local_repair_map_revision;
END;
CREATE TEMP TRIGGER local_repair_photo_update AFTER UPDATE OF id_local,fileFormat ON main.Adobe_images
 WHEN OLD.id_local IS NOT NEW.id_local OR OLD.fileFormat IS NOT NEW.fileFormat BEGIN
 UPDATE local_repair_map_revision SET revision=revision+1;
 INSERT INTO local_repair_map_journal SELECT revision,OLD.id_local FROM local_repair_map_revision;
 INSERT INTO local_repair_map_journal SELECT revision,NEW.id_local FROM local_repair_map_revision;
END;
