from .manager import StructureManagerWidget


class SuperStructureWidget(StructureManagerWidget):
    def __init__(self, controller):
        super().__init__(
            controller=controller,
            chunk_name="str_super_structure",
            default_components=[
                "Girders",
                "Deck Slab",
                "Expansion Joints",
                "Wearing Coat",
                "Parapets",
                "Diaphragm",
                "Cross Bracings"
            ],
        )
