
package com.tataloocode.editor

import android.webkit.JavascriptInterface

class EditorBridge(
    private val onCodeChanged: (String) -> Unit
) {
    @JavascriptInterface
    fun onCodeChanged(code: String) {
        onCodeChanged.invoke(code)
    }
}
