package cn.trailsnap.app;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class GalleryBackupPluginTest {
    @Test
    public void captureTimesWithinOneMinuteCanBePaired() {
        assertTrue(GalleryBackupPlugin.hasCompatibleCaptureTime(1_000_000L, 1_059_999L));
    }

    @Test
    public void captureTimesMoreThanOneMinuteApartAreRejected() {
        assertFalse(GalleryBackupPlugin.hasCompatibleCaptureTime(1_000_000L, 1_060_001L));
    }

    @Test
    public void missingVendorCaptureTimeRemainsCompatible() {
        assertTrue(GalleryBackupPlugin.hasCompatibleCaptureTime(0L, 1_000_000L));
    }
}
