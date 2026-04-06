{
  description = "TaskPlanner CLI binary built with Nuitka";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      python = pkgs.python313;
      pythonPkgs = python.pkgs;

      pythonEnv = python.withPackages (ps: with ps; [
        click
        httpx
        pyyaml
        nuitka
        zstandard
        ordered-set
      ]);
    in
    {
      packages.${system}.default = pkgs.stdenv.mkDerivation {
        pname = "taskplanner-cli";
        version = (builtins.fromTOML (builtins.readFile ./pyproject.toml)).project.version;

        src = ./.;

        nativeBuildInputs = [ pythonEnv pkgs.patchelf pkgs.autoPatchelfHook ];
        buildInputs = [ pkgs.zlib pkgs.libyaml pkgs.stdenv.cc.cc.lib ];

        buildPhase = ''
          export HOME=$TMPDIR
          # --no-onefile: nix sandbox breaks onefile payload attachment
          ${pythonEnv}/bin/python build/build_cli.py --no-onefile
        '';

        installPhase = ''
          mkdir -p $out/bin
          cp -r dist/cli.dist/* $out/bin/
        '';
      };

      devShells.${system}.default = pkgs.mkShell {
        packages = [ pythonEnv pkgs.patchelf ];
      };
    };
}
