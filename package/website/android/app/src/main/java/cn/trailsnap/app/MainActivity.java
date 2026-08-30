package cn.trailsnap.app;

import com.getcapacitor.BridgeActivity;
import android.os.Bundle;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(GalleryBackupPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
