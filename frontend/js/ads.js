class FOURXAdsController {
    constructor() {
        this.visible = false;
        this.refreshing = false;
        window.addEventListener("fourx-premium-status", () => this.refresh());
        document.addEventListener("visibilitychange", () => this.refresh());
        setTimeout(() => this.refresh(), 0);
    }

    async refresh() {
        if (this.refreshing) return;
        const plugin = window.Capacitor?.Plugins?.FourXAds;
        const shouldShow = window.Capacitor?.getPlatform?.() === "android"
            && window.app?.currentView === "view-home"
            && window.FOURXSubscription?.premium !== true
            && document.visibilityState === "visible";
        if (!plugin) return;
        this.refreshing = true;
        try {
            if (shouldShow && !this.visible) {
                await plugin.showBanner();
                this.visible = true;
            } else if (!shouldShow && this.visible) {
                await plugin.hideBanner();
                this.visible = false;
            }
        } catch (error) {
            console.error("Could not update the Android test-ad banner.", error);
        } finally {
            this.refreshing = false;
        }
    }
}

window.FOURXAds = new FOURXAdsController();
