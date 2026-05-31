package com.kesittayini.app;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ProgressBar;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

public class MainActivity extends AppCompatActivity {

    private static final String TAG = "KesitTayini";
    private WebView webView;
    private ProgressBar loader;
    private boolean pageLoaded = false;
    private Handler timeoutHandler;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webview);
        loader = findViewById(R.id.loader);
        timeoutHandler = new Handler(Looper.getMainLooper());

        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setLoadWithOverviewMode(true);
        webView.getSettings().setUseWideViewPort(true);
        webView.getSettings().setBuiltInZoomControls(false);
        webView.setWebChromeClient(new WebChromeClient());

        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }
        startFlaskServer();
    }

    private void showError(String title, String message) {
        webView.loadData(
            "<html><body style='padding:20px;font-family:sans-serif;background:#1a2744;color:#fff;'>" +
            "<h2>" + title + "</h2><pre style='white-space:pre-wrap;color:#ff6b6b;'>" +
            message + "</pre></body></html>",
            "text/html", "UTF-8"
        );
    }

    private void startFlaskServer() {
        new Thread(() -> {
            try {
                Python py = Python.getInstance();
                py.getModule("app").callAttr("start_flask", getFilesDir().getAbsolutePath());
                Log.i(TAG, "start_flask returned (Flask running in background)");

                for (int i = 0; i < 30; i++) {
                    try { Thread.sleep(1000); } catch (InterruptedException e) { break; }
                    if (pageLoaded) return;
                }

                if (!pageLoaded) {
                    runOnUiThread(() -> showError("Zaman Aşımı",
                        "Flask sunucusu 30 saniye içinde yanıt vermedi.\n" +
                        "Telefon modeli: " + android.os.Build.MODEL + "\n" +
                        "Android sürümü: " + android.os.Build.VERSION.SDK_INT));
                }
            } catch (Exception e) {
                Log.e(TAG, "Flask start failed", e);
                final String errorMsg = Log.getStackTraceString(e);
                runOnUiThread(() -> showError("Python Hatası", errorMsg));
            }
        }).start();

        timeoutHandler.postDelayed(() -> {
            if (!pageLoaded) {
                webView.loadUrl("http://127.0.0.1:5001");
                webView.setWebViewClient(new WebViewClient() {
                    @Override
                    public void onPageFinished(WebView view, String url) {
                        pageLoaded = true;
                        loader.setVisibility(android.view.View.GONE);
                    }
                    @Override
                    public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                        showError("WebView Hatası (" + errorCode + ")", description);
                    }
                });
            }
        }, 2500);
    }
}
