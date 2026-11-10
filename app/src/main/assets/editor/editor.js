
import { EditorView, basicSetup } from "https://esm.sh/codemirror@6.0.1";
import { EditorState } from "https://esm.sh/@codemirror/state@6.5.2";
import { python } from "https://esm.sh/@codemirror/lang-python@6.2.1";
import { javascript } from "https://esm.sh/@codemirror/lang-javascript@6.2.2";
import { html } from "https://esm.sh/@codemirror/lang-html@6.4.9";
import { css } from "https://esm.sh/@codemirror/lang-css@6.3.1";
import { json } from "https://esm.sh/@codemirror/lang-json@6.4.0";
import { oneDark } from "https://esm.sh/@codemirror/theme-one-dark@6.1.2";

let view;

function getLanguage(name) {
    const ext = name.split(".").pop().toLowerCase();

    switch (ext) {
        case "py": return python();
        case "js": return javascript();
        case "html": return html();
        case "css": return css();
        case "json": return json();
        default: return [];
    }
}

window.createTatalooEditor = function(code, fileName) {
    const parent = document.getElementById("editor");

    if (view) view.destroy();

    view = new EditorView({
        state: EditorState.create({
            doc: code || "",
            extensions: [
                basicSetup,
                getLanguage(fileName || "main.py"),
                oneDark,
                EditorView.updateListener.of(update => {
                    if (update.docChanged) {
                        if (window.TatalooBridge) {
                            window.TatalooBridge.onCodeChanged(
                                update.state.doc.toString()
                            );
                        }
                    }
                })
            ]
        }),
        parent
    });
};

window.setEditorCode = function(code) {
    if (!view) return;

    const current = view.state.doc.toString();

    if (current === code) return;

    view.dispatch({
        changes: {
            from: 0,
            to: current.length,
            insert: code || ""
        }
    });
};

window.getEditorCode = function() {
    return view ? view.state.doc.toString() : "";
};
