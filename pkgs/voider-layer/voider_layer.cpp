// Thin C++ Python extension: configures voider-py's QMainWindow as a
// wlr-layer-shell Layer::Bottom surface via layer-shell-qt.
//
// Called from voider.py after the window is shown:
//   import voider_layer, PyQt6.sip as sip
//   voider_layer.configure(sip.unwrapinstance(window.windowHandle()))

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <QWindow>
#include <LayerShellQt/window.h>

static PyObject *configure(PyObject *, PyObject *arg) {
    void *ptr = PyLong_AsVoidPtr(arg);
    if (!ptr && PyErr_Occurred()) return nullptr;

    QWindow *win = static_cast<QWindow *>(ptr);
    win->create();  // ensure the native Wayland surface exists

    LayerShellQt::Window *lw = LayerShellQt::Window::get(win);
    if (!lw) {
        PyErr_SetString(PyExc_RuntimeError,
            "LayerShellQt::Window::get() returned null — "
            "check QT_WAYLAND_SHELL_INTEGRATION=layer-shell and that "
            "layer-shell-qt plugin is on QT_PLUGIN_PATH");
        return nullptr;
    }

    using W = LayerShellQt::Window;
    lw->setLayer(W::LayerBottom);
    lw->setAnchors(W::Anchors(W::AnchorLeft | W::AnchorRight | W::AnchorTop | W::AnchorBottom));
    lw->setExclusiveZone(0);
    lw->setKeyboardInteractivity(W::KeyboardInteractivityOnDemand);

    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"configure", configure, METH_O, "Configure QWindow as Layer::Bottom surface"},
    {nullptr, nullptr, 0, nullptr}
};

static struct PyModuleDef mod = {
    PyModuleDef_HEAD_INIT, "voider_layer", nullptr, -1, methods
};

PyMODINIT_FUNC PyInit_voider_layer() {
    return PyModule_Create(&mod);
}
