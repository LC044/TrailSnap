package cn.trailsnap.app;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.assertEquals;

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

    @Test
    public void freshScanBaselinesHistoricalCompanionVideosOnlyOnce() {
        assertTrue(GalleryBackupPlugin.shouldInitializeCompanionCursor(0L, 0L, 0L));
        assertFalse(GalleryBackupPlugin.shouldInitializeCompanionCursor(10L, 0L, 0L));
        assertFalse(GalleryBackupPlugin.shouldInitializeCompanionCursor(0L, 1_000L, 2L));
    }

    @Test
    public void mediaStoreDateAddedIsUsedWhenDateTakenIsMissing() {
        assertEquals(1_700_000_000_123L, GalleryBackupPlugin.chooseTakenMs(1_700_000_000_123L, 42L));
        assertEquals(1_700_000_000_000L, GalleryBackupPlugin.chooseTakenMs(0L, 1_700_000_000L));
    }
}
