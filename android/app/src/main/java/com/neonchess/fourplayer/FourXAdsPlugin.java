package com.neonchess.fourplayer;

import android.graphics.Color;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.FrameLayout;

import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.google.android.gms.ads.AdRequest;
import com.google.android.gms.ads.AdSize;
import com.google.android.gms.ads.AdView;
import com.google.android.gms.ads.MobileAds;

@CapacitorPlugin(name = "FourXAds")
public class FourXAdsPlugin extends Plugin {
    private static final String TEST_BANNER_UNIT_ID = "ca-app-pub-3940256099942544/6300978111";
    private AdView banner;

    @PluginMethod
    public void showBanner(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            if (banner == null) {
                MobileAds.initialize(getContext());
                banner = new AdView(getContext());
                banner.setAdSize(AdSize.BANNER);
                banner.setAdUnitId(TEST_BANNER_UNIT_ID);
                banner.setBackgroundColor(Color.TRANSPARENT);
                FrameLayout content = getActivity().findViewById(android.R.id.content);
                FrameLayout.LayoutParams params = new FrameLayout.LayoutParams(
                        ViewGroup.LayoutParams.WRAP_CONTENT,
                        ViewGroup.LayoutParams.WRAP_CONTENT,
                        Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL
                );
                params.bottomMargin = (int) (68 * getContext().getResources()
                        .getDisplayMetrics().density);
                content.addView(banner, params);
                banner.loadAd(new AdRequest.Builder().build());
            }
            call.resolve();
        });
    }

    @PluginMethod
    public void hideBanner(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            if (banner != null) {
                ViewGroup parent = (ViewGroup) banner.getParent();
                if (parent != null) parent.removeView(banner);
                banner.destroy();
                banner = null;
            }
            call.resolve();
        });
    }
}
