package com.kesittayini.app;

import android.os.Bundle;
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

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webview);
        loader = findViewById(R.id.loader);

        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setLoadWithOverviewMode(true);
        webView.getSettings().setUseWideViewPort(true);
        webView.getSettings().setBuiltInZoomControls(false);
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                loader.setVisibility(android.view.View.GONE);
            }
            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                Log.e(TAG, "WebView error: " + description);
                webView.loadData(
                    "<html><body style='padding:20px;font-family:sans-serif;background:#1a2744;color:#fff;'>" +
                    "<h2>Sunucu başlatılamadı</h2>" +
                    "<p>Hata: " + description + "</p>" +
                    "<p>Kod: " + errorCode + "</p>" +
                    "</body></html>",
                    "text/html", "UTF-8"
                );
            }
        });

        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }
        startFlaskServer();
    }

    private void startFlaskServer() {
        new Thread(() -> {
            try {
                Python py = Python.getInstance();
                py.getModule("app").callAttr("start_flask", getFilesDir().getAbsolutePath());
                Log.i(TAG, "Flask started successfully");

                try {
                    Thread.sleep(1500);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }

                runOnUiThread(() -> webView.loadUrl("http://127.0.0.1:5001"));
            } catch (Exception e) {
                Log.e(TAG, "Flask start failed", e);
                final String errorMsg = Log.getStackTraceString(e);
                runOnUiThread(() -> {
                    Toast.makeText(MainActivity.this, "Hata: " + e.getMessage(), Toast.LENGTH_LONG).show();
                    webView.loadData(
                        "<html><body style='padding:20px;font-family:sans-serif;background:#1a2744;color:#fff;'>" +
                        "<h2>Python Hatası</h2><pre style='white-space:pre-wrap;color:#ff6b6b;'>" +
                        errorMsg + "</pre></body></html>",
                        "text/html", "UTF-8"
                    );
                });
            }
        }).start();
    }
}
