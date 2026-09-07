r"""MDR Automation Tool - backend.

Layering (dependencies point downward only):

    api  ->  services  ->  engine  ->  domain
                  \-> infrastructure -/

`domain` imports nothing from the layers above it and knows nothing about
FastAPI, openpyxl or React. `engine` holds the MDR business rules. The engine
is usable with nothing but a workbook path - see `services.mdr_pipeline`.
"""

__version__ = "0.2.0"
