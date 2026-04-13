{
  description = "TaskPlanner - task planning system with CLI and server";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      python = pkgs.python313;
    in
    {
      packages.${system}.default = python.pkgs.buildPythonApplication {
        pname = "task-planner";
        version = (builtins.fromTOML (builtins.readFile ./pyproject.toml)).project.version;
        pyproject = true;

        src = ./.;

        build-system = [ python.pkgs.hatchling ];

        dependencies = with python.pkgs; [
          click
          httpx
          pyyaml
          pydantic
          fastapi
          uvicorn
          python-multipart
        ];

        preBuild = ''
          # Remove stale build artifacts copied from source tree
          rm -rf dist
          # Web client not built here — create placeholder so hatchling succeeds
          mkdir -p client_web/dist/assets
          touch client_web/dist/index.html
        '';
      };

      devShells.${system}.default = pkgs.mkShell {
        packages = [
          (python.withPackages (ps: with ps; [
            click httpx pyyaml pydantic fastapi uvicorn python-multipart
            nuitka ordered-set
          ]))
          pkgs.patchelf
        ];
      };
    };
}
