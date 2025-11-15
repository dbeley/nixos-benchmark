{ pkgs ? import <nixpkgs> {} }:

let
  pythonPackages = pkgs.python3Packages;
in pkgs.mkShell {
  buildInputs = with pkgs; [
    p7zip
    stress-ng
    fio
    glmark2
    openssl
    speedtest-cli
    ffmpeg
    x264
    sqlite
    php
    gnumake
  ];
}
