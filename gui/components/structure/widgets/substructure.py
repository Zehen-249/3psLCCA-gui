from .manager import StructureManagerWidget

class SubStructureWidget(StructureManagerWidget):
    def __init__(self, controller):
        StructureManagerWidget.__init__(
            self,
            controller=controller,
            chunk_name="str_sub_structure",
            default_components=["Abutment", "Pier", "Pier Cap", "Pedestal", "Bearing"]
        )