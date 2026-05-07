"""nir/materials.py -- VBA generators for NIR-band materials (Au, Ag, SiO2).

Writes two material models for each metal:
  - "Au_lossy" / "Ag_lossy": constant-sigma lossy metal (proven, matches mid-IR pattern).
    Use this for first-pass simulations where peak POSITION matters.
  - "Au_Drude" / "Ag_Drude": Drude dispersion model with Johnson & Christy fit
    parameters. More accurate FWHM/amplitude at NIR. Available in CST after
    geometry build but NOT referenced by default -- swap material names in
    geometry_disk.py to activate.

Why both: the constant-sigma definitions are guaranteed to compile in any CST
version, so the agent loop never stalls on a VBA error. Dispersive materials
are written alongside so they're immediately usable for accuracy comparisons
once the Drude VBA syntax is confirmed in this CST install.

Refs:
  - Constant-sigma (DC) values: Au 4.1e7, Ag 6.3e7 S/m. Matches run_midIR_v3.py.
  - Johnson & Christy Drude fit, optical band:
      Au: omega_p = 1.367e16 rad/s, gamma = 1.05e14 rad/s
      Ag: omega_p = 1.367e16 rad/s, gamma = 2.73e13 rad/s
  - SiO2 at NIR: n=1.45 -> epsilon_r = 2.10, tan_delta ~= 0.0
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Constant-sigma lossy-metal definitions (default, referenced by geometry)
# ---------------------------------------------------------------------------

def _lossy_metal_block(name: str, sigma: float, colour: tuple[str, str, str]) -> str:
    return "\n".join([
        "With Material",
        "  .Reset",
        f'  .Name "{name}"',
        '  .Folder ""',
        '  .FrqType "all"',
        '  .Type "Lossy metal"',
        f'  .Sigma "{sigma}"',
        f'  .Colour "{colour[0]}", "{colour[1]}", "{colour[2]}"',
        "  .Create",
        "End With",
    ])


def _normal_dielectric_block(name: str, eps: float, tand: float,
                             colour: tuple[str, str, str]) -> str:
    return "\n".join([
        "With Material",
        "  .Reset",
        f'  .Name "{name}"',
        '  .Folder ""',
        '  .FrqType "all"',
        '  .Type "Normal"',
        f'  .Epsilon "{eps}"',
        '  .Mu "1"',
        '  .Kappa "0"',
        f'  .TanD "{tand}"',
        '  .TanDGiven "True"',
        '  .TanDModel "ConstTanD"',
        f'  .Colour "{colour[0]}", "{colour[1]}", "{colour[2]}"',
        "  .Create",
        "End With",
    ])


def _drude_metal_block(name: str, eps_inf: float, omega_p: float, gamma: float,
                       colour: tuple[str, str, str]) -> str:
    """Best-guess Drude VBA. May need tweaking for specific CST versions."""
    return "\n".join([
        "' --- Drude dispersion (NIR-band, J&C fit) ---",
        "With Material",
        "  .Reset",
        f'  .Name "{name}"',
        '  .Folder ""',
        '  .FrqType "all"',
        '  .Type "Normal"',
        f'  .Epsilon "{eps_inf}"',
        '  .Mu "1"',
        '  .Sigma "0"',
        '  .DispModelEpsilon "Drude"',
        f'  .EpsInfinity "{eps_inf}"',
        f'  .DispCoeff1Eps "{omega_p}"',
        f'  .DispCoeff2Eps "{gamma}"',
        f'  .Colour "{colour[0]}", "{colour[1]}", "{colour[2]}"',
        "  .Create",
        "End With",
    ])


def build_nir_materials_vba() -> str:
    """Generate the full materials VBA block for the NIR disk-MIM absorber.

    Defines (in order):
      1. Au_lossy           -- constant sigma, used by default in geometry
      2. Ag_lossy           -- constant sigma, used by default in geometry
      3. SiO2               -- normal dielectric, eps=2.10
      4. Au_Drude           -- dispersive (alternative; not auto-referenced)
      5. Ag_Drude           -- dispersive (alternative; not auto-referenced)
    """
    return "\n\n".join([
        # Default working materials
        _lossy_metal_block("Au_lossy", sigma=4.1e7,
                           colour=("1.0", "0.84", "0.0")),
        _lossy_metal_block("Ag_lossy", sigma=6.3e7,
                           colour=("0.85", "0.85", "0.9")),
        _normal_dielectric_block("SiO2", eps=2.10, tand=0.0,
                                 colour=("0.8", "0.8", "0.95")),

        # Alternative dispersive materials (defined but not referenced)
        _drude_metal_block("Au_Drude", eps_inf=1.0,
                           omega_p=1.367e16, gamma=1.05e14,
                           colour=("0.95", "0.78", "0.05")),
        _drude_metal_block("Ag_Drude", eps_inf=1.0,
                           omega_p=1.367e16, gamma=2.73e13,
                           colour=("0.75", "0.75", "0.85")),
    ])


def build_nir_materials_vba_constant_only() -> str:
    """Constant-sigma only (no Drude). Use as a fallback if Drude syntax errors
    block the history rebuild."""
    return "\n\n".join([
        _lossy_metal_block("Au_lossy", sigma=4.1e7,
                           colour=("1.0", "0.84", "0.0")),
        _lossy_metal_block("Ag_lossy", sigma=6.3e7,
                           colour=("0.85", "0.85", "0.9")),
        _normal_dielectric_block("SiO2", eps=2.10, tand=0.0,
                                 colour=("0.8", "0.8", "0.95")),
    ])


def build_nir_materials_vba_with_cr() -> str:
    """Add Cr (constant sigma 7.7e6 S/m) to the constant-only material set.
    Used by hypothesis C (planar MIM) which uses a thin Cr semi-transparent
    top layer to broaden the Fabry-Perot absorption."""
    return "\n\n".join([
        _lossy_metal_block("Au_lossy", sigma=4.1e7,
                           colour=("1.0", "0.84", "0.0")),
        _lossy_metal_block("Ag_lossy", sigma=6.3e7,
                           colour=("0.85", "0.85", "0.9")),
        _lossy_metal_block("Cr_lossy", sigma=7.7e6,
                           colour=("0.4", "0.4", "0.45")),
        _normal_dielectric_block("SiO2", eps=2.10, tand=0.0,
                                 colour=("0.8", "0.8", "0.95")),
    ])
