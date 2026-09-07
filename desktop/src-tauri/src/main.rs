// Pas de console sur Windows en release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    freesolid_desktop_lib::run()
}
