package com.neonchess.fourplayer;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(android.os.Bundle savedInstanceState) {
        registerPlugin(PlayBillingPlugin.class);
        registerPlugin(FourXAdsPlugin.class);
        super.onCreate(savedInstanceState);
    }}
