package cn.trailsnap.app;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class GalleryBackupPluginTest {
    @Test
    public void appleFixtureNamesCanBePaired() {
        assertTrue(GalleryBackupPlugin.isSupportedLivePairName("IMG_4669.HEIC", "IMG_4669.MOV"));
    }

    @Test
    public void androidFixtureNamesCanBePaired() {
        assertTrue(GalleryBackupPlugin.isSupportedLivePairName(
            "IMG_20250510_114039.jpg", "IMG_20250510_114039.mp4"
        ));
    }

    @Test
    public void pairNamesAreCaseInsensitive() {
        assertTrue(GalleryBackupPlugin.isSupportedLivePairName("trip.JPEG", "TRIP.mov"));
    }

    @Test
    public void differentStemsAreRejected() {
        assertFalse(GalleryBackupPlugin.isSupportedLivePairName("IMG_0001.jpg", "IMG_0002.mp4"));
    }

    @Test
    public void unsupportedExtensionsAreRejected() {
        assertFalse(GalleryBackupPlugin.isSupportedLivePairName("IMG_0001.png", "IMG_0001.mp4"));
        assertFalse(GalleryBackupPlugin.isSupportedLivePairName("IMG_0001.heic", "IMG_0001.mp4"));
    }
}
