from frappe.model.document import Document

from calco_erp.calco_production.production_execution import FGDeliveryNoteMixin


class FGDeliveryNote(FGDeliveryNoteMixin, Document):
    pass

