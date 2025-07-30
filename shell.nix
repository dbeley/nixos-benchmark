{ pkgs ? import <nixpkgs> {} }:

let
  pythonPackages = pkgs.python3Packages;
in pkgs.mkShell {
  buildInputs = with pkgs; [
    phoronix-test-suite
    bison flex gmp libaio SDL2 zlib openssl
    php nginx
    python3
    pythonPackages.pip
    pythonPackages.distutils
    pythonPackages.pyyaml
    pythonPackages.numpy
    pythonPackages.cython
  ];
}
