class FOURXSubscriptionController {
    constructor() {
        this.configured = false;
        this.premium = false;
        this.subscription = null;
        this.products = [];
        this.androidProductsReady = false;
        this.statusMessage = "Checking subscription status…";
        this.purchaseBusy = false;
        this.billing = window.Capacitor?.Plugins?.PlayBilling || null;
        this.bindEvents();
        this.bindBillingEvents();
        this.initialize();
    }

    bindEvents() {
        document.querySelectorAll("[data-subscribe-product]").forEach(button => {
            button.addEventListener("click", () => this.subscribe(button.dataset.subscribeProduct));
        });
        document.getElementById("premium-restore")?.addEventListener("click", () => this.restore());
        document.getElementById("premium-manage")?.addEventListener("click", () => this.manage());
        document.addEventListener("visibilitychange", () => {
            if (!document.hidden && this.premium) this.refreshStatus();
        });
    }

    bindBillingEvents() {
        if (!this.billing?.addListener) return;
        this.billing.addListener("purchaseUpdated", event => this.onPurchaseUpdated(event))
            .catch(error => {
                console.error("Could not register Google Play purchase updates.", error);
            });
    }

    async initialize() {
        try {
            await window.FOURXProfile?.ready;
            await this.refreshStatus();
            await this.loadProducts();
        } catch (error) {
            this.statusMessage = `Subscription status unavailable: ${error.message}`;
            this.render();
            this.notifyPremiumChange();
        }
    }

    async refreshStatus() {
        try {
            await window.FOURXProfile?.ready;
            const result = await window.FOURXProfile.request("/api/subscription/status");
            this.configured = result.configured === true;
            this.premium = result.premium === true;
            this.subscription = result.subscription || null;
            this.statusMessage = this.premium
                ? "FOURX Premium is active."
                : this.configured
                    ? "No active Premium subscription."
                    : "Google Play verification is not configured yet.";
            this.render();
            this.notifyPremiumChange();
            window.FOURXAds?.refresh();
            return result;
        } catch (error) {
            this.premium = false;
            this.subscription = null;
            this.statusMessage = `Could not verify subscription status: ${error.message}`;
            this.render();
            this.notifyPremiumChange();
            window.FOURXAds?.refresh();
            throw error;
        }
    }

    async refreshStatusQuietly() {
        try {
            await this.refreshStatus();
        } catch (error) {
            console.error("Could not refresh Premium status.", error);
        }
    }

    async onOpen() {
        await this.refreshStatusQuietly();
        await this.loadProducts();
    }

    async loadProducts() {
        try {
            const catalog = await window.FOURXProfile.request("/api/subscription/products");
            this.configured = catalog.configured === true;
            this.products = Array.isArray(catalog.products) ? catalog.products : [];
            if (!this.configured || !this.billing) {
                this.androidProductsReady = false;
                this.render();
                return;
            }
            const result = await this.billing.loadProducts({
                productIds: this.products.map(product => product.product_id),
            });
            const nativeProducts = new Map(
                (result.products || []).map(product => [product.productId, product]),
            );
            this.androidProductsReady = this.products.length === 2
                && this.products.every(product => {
                    const native = nativeProducts.get(product.product_id);
                    return native
                        && native.priceCurrencyCode === product.currency
                        && native.priceAmountMicros === product.price_minor * 10000;
                });
            if (!this.androidProductsReady) {
                this.statusMessage = "Google Play product prices do not match the published INR plans.";
            }
            this.render();
        } catch (error) {
            this.androidProductsReady = false;
            this.statusMessage = `Google Play products unavailable: ${error.message}`;
            this.render();
        }
    }

    async subscribe(productId) {
        if (!this.configured) {
            this.setNotice("Subscriptions are unavailable until secure Google Play verification is configured.");
            return;
        }
        if (!this.billing) {
            this.setNotice("Subscriptions can only be purchased in the FOURX Android app through Google Play.");
            return;
        }
        if (!this.androidProductsReady) {
            await this.loadProducts();
            if (!this.androidProductsReady) return;
        }
        if (this.premium) {
            this.setNotice("Premium is already active. Use Manage Subscription to change or cancel renewal.");
            return;
        }
        const profile = window.FOURXProfile?.profile;
        if (!profile?.id) {
            this.setNotice("A profile is required before starting a subscription.");
            return;
        }
        this.purchaseBusy = true;
        this.render();
        try {
            await this.billing.purchase({ productId, profileId: profile.id });
            this.setNotice("Google Play purchase flow opened. Premium activates only after server verification.");
        } catch (error) {
            this.setNotice(`Google Play could not start the purchase: ${error.message}`);
        } finally {
            this.purchaseBusy = false;
            this.render();
        }
    }

    async onPurchaseUpdated(event) {
        if (!event || event.status === "purchase_flow_started") return;
        if (event.status === "canceled") {
            this.setNotice("Purchase canceled. No subscription was started.");
            return;
        }
        if (event.status === "pending") {
            this.setNotice("Payment is pending. Premium stays locked until Google Play confirms it.");
            return;
        }
        if (event.status === "failed") {
            this.setNotice(event.message || "Google Play did not complete the purchase.");
            return;
        }
        if (event.status !== "purchased"
            || typeof event.productId !== "string"
            || typeof event.purchaseToken !== "string") {
            this.setNotice("Google Play returned an incomplete purchase. Premium remains locked.");
            return;
        }
        try {
            this.setNotice("Verifying purchase securely with Google Play…");
            const result = await window.FOURXProfile.request("/api/subscription/verify", {
                method: "POST",
                body: JSON.stringify({
                    product_id: event.productId,
                    purchase_token: event.purchaseToken,
                }),
            });
            if (result.status === "pending") {
                this.setNotice("Payment is pending. Premium stays locked until Google Play confirms it.");
            } else if (result.premium) {
                this.setNotice("Google Play verified your subscription. Premium is active.");
            } else {
                this.setNotice("Google Play has not confirmed an active subscription yet.");
            }
            await this.refreshStatus();
        } catch (error) {
            this.setNotice(`Purchase verification failed; Premium was not enabled: ${error.message}`);
        }
    }

    async restore() {
        if (!this.billing) {
            this.setNotice("Restore Purchases is available in the FOURX Android app.");
            return;
        }
        if (!this.configured) {
            this.setNotice("Restore is unavailable until secure Google Play verification is configured.");
            return;
        }
        const button = document.getElementById("premium-restore");
        if (button) button.disabled = true;
        try {
            const result = await this.billing.restorePurchases();
            const purchases = result.purchases || [];
            const purchased = purchases.filter(item => item.status === "purchased");
            for (const purchase of purchased) await this.onPurchaseUpdated(purchase);
            if (!purchased.length) {
                const pending = purchases.some(item => item.status === "pending");
                this.setNotice(pending
                    ? "A Google Play payment is pending; Premium remains locked."
                    : "Google Play did not find an active FOURX Premium purchase.");
            }
            await this.refreshStatus();
        } catch (error) {
            this.setNotice(`Could not restore purchases: ${error.message}`);
        } finally {
            if (button) button.disabled = false;
        }
    }

    manage() {
        const productId = this.subscription?.product_id || "fourx_premium_monthly";
        const url = new URL("https://play.google.com/store/account/subscriptions");
        url.searchParams.set("sku", productId);
        url.searchParams.set("package", "com.neonchess.fourplayer");
        window.open(url.toString(), "_blank", "noopener,noreferrer");
    }

    setNotice(message) {
        const notice = document.getElementById("premium-notice");
        if (notice) notice.textContent = message;
    }

    render() {
        const status = document.getElementById("premium-current-status");
        if (status) {
            if (this.premium && this.subscription) {
                const expiry = new Date(this.subscription.expires_at);
                const expiryLabel = Number.isNaN(expiry.getTime())
                    ? "unknown"
                    : new Intl.DateTimeFormat(undefined, {
                        dateStyle: "medium",
                        timeStyle: "short",
                    }).format(expiry);
                status.textContent = `Premium active until ${expiryLabel}. ${
                    this.subscription.auto_renew_enabled
                        ? "Renews automatically."
                        : "Renewal is off; access continues until expiry."
                }`;
            } else {
                status.textContent = this.statusMessage;
            }
        }
        document.querySelectorAll("[data-subscribe-product]").forEach(button => {
            button.disabled = this.purchaseBusy || this.premium || !this.configured;
            if (this.premium) button.textContent = "Premium Active";
            else if (!this.configured) button.textContent = "Not Available";
            else button.textContent = button.dataset.subscribeProduct === "fourx_premium_yearly"
                ? "Subscribe Yearly"
                : "Subscribe Monthly";
        });
    }

    notifyPremiumChange() {
        window.dispatchEvent(new CustomEvent("fourx-premium-status", {
            detail: { premium: this.premium, configured: this.configured },
        }));
    }
}

window.FOURXSubscription = new FOURXSubscriptionController();
