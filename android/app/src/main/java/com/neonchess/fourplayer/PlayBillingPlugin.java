package com.neonchess.fourplayer;

import com.android.billingclient.api.BillingClient;
import com.android.billingclient.api.BillingClientStateListener;
import com.android.billingclient.api.BillingFlowParams;
import com.android.billingclient.api.BillingResult;
import com.android.billingclient.api.PendingPurchasesParams;
import com.android.billingclient.api.ProductDetails;
import com.android.billingclient.api.ProductDetailsResponseListener;
import com.android.billingclient.api.Purchase;
import com.android.billingclient.api.PurchasesResponseListener;
import com.android.billingclient.api.QueryProductDetailsParams;
import com.android.billingclient.api.QueryProductDetailsResult;
import com.android.billingclient.api.QueryPurchasesParams;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@CapacitorPlugin(name = "PlayBilling")
public class PlayBillingPlugin extends Plugin {
    private static final String MONTHLY_PRODUCT = "fourx_premium_monthly";
    private static final String YEARLY_PRODUCT = "fourx_premium_yearly";
    private BillingClient billingClient;
    private final Map<String, ProductDetails> productDetailsById = new HashMap<>();

    @Override
    public void load() {
        billingClient = BillingClient.newBuilder(getContext())
                .setListener(this::onPurchasesUpdated)
                .enablePendingPurchases(
                        PendingPurchasesParams.newBuilder()
                                .enableOneTimeProducts()
                                .enablePrepaidPlans()
                                .build()
                )
                .enableAutoServiceReconnection()
                .build();
    }

    @PluginMethod
    public void loadProducts(PluginCall call) {
        JSArray productIds = call.getArray("productIds");
        if (productIds == null || productIds.length() == 0) {
            call.reject("Subscription product IDs are required.");
            return;
        }
        List<QueryProductDetailsParams.Product> products = new ArrayList<>();
        for (int index = 0; index < productIds.length(); index++) {
            String productId = productIds.optString(index);
            if (!isSupportedProduct(productId)) {
                call.reject("Unsupported subscription product.");
                return;
            }
            products.add(QueryProductDetailsParams.Product.newBuilder()
                    .setProductId(productId)
                    .setProductType(BillingClient.ProductType.SUBS)
                    .build());
        }

        connect(call, () -> {
            QueryProductDetailsParams params = QueryProductDetailsParams.newBuilder()
                    .setProductList(products)
                    .build();
            billingClient.queryProductDetailsAsync(params,
                    (BillingResult result, QueryProductDetailsResult response) -> {
                        if (result.getResponseCode() != BillingClient.BillingResponseCode.OK) {
                            call.reject("Google Play could not load subscription products.");
                            return;
                        }
                        productDetailsById.clear();
                        JSArray details = new JSArray();
                        for (ProductDetails product : response.getProductDetailsList()) {
                            productDetailsById.put(product.getProductId(), product);
                            JSObject item = new JSObject();
                            item.put("productId", product.getProductId());
                            item.put("title", product.getTitle());
                            item.put("description", product.getDescription());
                            List<ProductDetails.SubscriptionOfferDetails> offers =
                                    product.getSubscriptionOfferDetails();
                            if (offers != null && !offers.isEmpty()) {
                                List<ProductDetails.PricingPhase> phases =
                                        offers.get(0).getPricingPhases().getPricingPhaseList();
                                if (!phases.isEmpty()) {
                                    ProductDetails.PricingPhase recurringPhase =
                                            phases.get(phases.size() - 1);
                                    item.put("formattedPrice", recurringPhase.getFormattedPrice());
                                    item.put("billingPeriod", recurringPhase.getBillingPeriod());
                                    item.put("priceCurrencyCode", recurringPhase.getPriceCurrencyCode());
                                    item.put("priceAmountMicros", recurringPhase.getPriceAmountMicros());
                                }
                            }
                            details.put(item);
                        }
                        JSObject responseData = new JSObject();
                        responseData.put("products", details);
                        call.resolve(responseData);
                    });
        });
    }

    @PluginMethod
    public void purchase(PluginCall call) {
        String productId = call.getString("productId");
        String profileId = call.getString("profileId");
        if (!isSupportedProduct(productId) || profileId == null || profileId.isEmpty()) {
            call.reject("A supported subscription and profile are required.");
            return;
        }
        connect(call, () -> {
            ProductDetails product = productDetailsById.get(productId);
            if (product == null) {
                call.reject("Load Google Play subscription products before purchasing.");
                return;
            }
            List<ProductDetails.SubscriptionOfferDetails> offers =
                    product.getSubscriptionOfferDetails();
            if (offers == null || offers.isEmpty()) {
                call.reject("This subscription is not available in Google Play.");
                return;
            }
            String offerToken = offers.get(0).getOfferToken();
            if (offerToken == null || offerToken.isEmpty()) {
                call.reject("Google Play did not return a valid subscription offer.");
                return;
            }
            BillingFlowParams.ProductDetailsParams productParams =
                    BillingFlowParams.ProductDetailsParams.newBuilder()
                            .setProductDetails(product)
                            .setOfferToken(offerToken)
                            .build();
            BillingFlowParams flowParams = BillingFlowParams.newBuilder()
                    .setProductDetailsParamsList(Collections.singletonList(productParams))
                    .setObfuscatedAccountId(obfuscateProfileId(profileId))
                    .build();
            BillingResult result = billingClient.launchBillingFlow(getActivity(), flowParams);
            if (result.getResponseCode() != BillingClient.BillingResponseCode.OK) {
                if (result.getResponseCode() == BillingClient.BillingResponseCode.USER_CANCELED) {
                    notifyListeners("purchaseUpdated", event("canceled", null, null));
                    call.resolve(event("canceled", null, null));
                    return;
                }
                call.reject("Google Play could not start the purchase flow.");
                return;
            }
            call.resolve(event("purchase_flow_started", productId, null));
        });
    }

    @PluginMethod
    public void restorePurchases(PluginCall call) {
        connect(call, () -> {
            QueryPurchasesParams params = QueryPurchasesParams.newBuilder()
                    .setProductType(BillingClient.ProductType.SUBS)
                    .build();
            billingClient.queryPurchasesAsync(params, (PurchasesResponseListener)
                    (result, purchases) -> {
                        if (result.getResponseCode() != BillingClient.BillingResponseCode.OK) {
                            call.reject("Google Play could not restore purchases.");
                            return;
                        }
                        JSArray restored = new JSArray();
                        for (Purchase purchase : purchases) {
                            if (purchase.getProducts().contains(MONTHLY_PRODUCT)
                                    || purchase.getProducts().contains(YEARLY_PRODUCT)) {
                                restored.put(purchaseData(purchase));
                            }
                        }
                        JSObject response = new JSObject();
                        response.put("purchases", restored);
                        call.resolve(response);
                    });
        });
    }

    private void connect(PluginCall call, Runnable action) {
        if (billingClient.isReady()) {
            action.run();
            return;
        }
        billingClient.startConnection(new BillingClientStateListener() {
            @Override
            public void onBillingSetupFinished(BillingResult result) {
                if (result.getResponseCode() == BillingClient.BillingResponseCode.OK) {
                    action.run();
                } else {
                    call.reject("Google Play Billing is unavailable on this device.");
                }
            }

            @Override
            public void onBillingServiceDisconnected() {
                notifyListeners("billingDisconnected", new JSObject());
            }
        });
    }

    private void onPurchasesUpdated(BillingResult result, List<Purchase> purchases) {
        if (result.getResponseCode() == BillingClient.BillingResponseCode.USER_CANCELED) {
            notifyListeners("purchaseUpdated", event("canceled", null, null));
            return;
        }
        if (result.getResponseCode() != BillingClient.BillingResponseCode.OK || purchases == null) {
            JSObject failed = event("failed", null, null);
            failed.put("message", "Google Play did not complete the purchase.");
            notifyListeners("purchaseUpdated", failed);
            return;
        }
        for (Purchase purchase : purchases) {
            notifyListeners("purchaseUpdated", purchaseData(purchase));
        }
    }

    private JSObject purchaseData(Purchase purchase) {
        String state = purchase.getPurchaseState() == Purchase.PurchaseState.PURCHASED
                ? "purchased"
                : purchase.getPurchaseState() == Purchase.PurchaseState.PENDING
                        ? "pending"
                        : "unknown";
        String productId = purchase.getProducts().isEmpty()
                ? null
                : purchase.getProducts().get(0);
        JSObject data = event(state, productId, purchase.getPurchaseToken());
        data.put("acknowledged", purchase.isAcknowledged());
        return data;
    }

    private JSObject event(String state, String productId, String token) {
        JSObject data = new JSObject();
        data.put("status", state);
        if (productId != null) data.put("productId", productId);
        if (token != null) data.put("purchaseToken", token);
        return data;
    }

    private boolean isSupportedProduct(String productId) {
        return MONTHLY_PRODUCT.equals(productId) || YEARLY_PRODUCT.equals(productId);
    }

    private String obfuscateProfileId(String profileId) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(profileId.getBytes(StandardCharsets.UTF_8));
            StringBuilder result = new StringBuilder(digest.length * 2);
            for (byte value : digest) {
                result.append(String.format("%02x", value));
            }
            return result.toString();
        } catch (Exception error) {
            throw new IllegalStateException("Could not obfuscate profile ID.", error);
        }
    }
}
