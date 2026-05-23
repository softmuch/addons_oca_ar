# For copyright and license notices, see __manifest__.py file in module root
# directory or check the readme files

import logging

from OpenSSL import crypto

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AfipwsCertificateAlias(models.Model):
    _name = "afipws.certificate_alias"
    _description = "AFIP Distingish Name / Alias"
    _rec_name = "common_name"

    common_name = fields.Char(
        size=64,
        default="AFIP WS",
        help="Just a name, you can leave it this way",
        required=True,
    )
    key = fields.Text(
        "Private Key",
    )
    company_id = fields.Many2one(
        "res.company",
        "Company",
        required=True,
        default=lambda self: self.env.company,
        auto_join=True,
        index=True,
    )
    country_id = fields.Many2one(
        "res.country",
        "Country",
        required=True,
    )
    state_id = fields.Many2one(
        "res.country.state",
        "State",
    )
    city = fields.Char(
        required=True,
    )
    department = fields.Char(
        default="IT",
        required=True,
    )
    cuit = fields.Char(
        "CUIT",
        compute="_compute_cuit",
        required=True,
    )
    company_cuit = fields.Char(
        "Company CUIT",
        size=16,
    )
    service_provider_cuit = fields.Char(
        "Service Provider CUIT",
        size=16,
    )
    certificate_ids = fields.One2many(
        "afipws.certificate",
        "alias_id",
        "Certificates",
        auto_join=True,
    )
    service_type = fields.Selection(
        [("in_house", "En Casa"), ("outsourced", "Subcontratado")],
        default="in_house",
        required=True,
    )
    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("confirmed", "Confirmado"),
            ("cancel", "Cancelado"),
        ],
        "Status",
        index=True,
        readonly=True,
        default="draft",
        help="* The 'Draft' state is used when a user is creating a new pair "
        "key. Warning: everybody can see the key."
        "\n* The 'Confirmed' state is used when the key is completed with "
        "public or private key."
        "\n* The 'Canceled' state is used when the key is not more used. "
        "You cant use this key again.",
    )
    type = fields.Selection(
        [("production", "Producción"), ("homologation", "Homologación")],
        required=True,
        default="production",
    )

    @api.onchange("company_id")
    def change_company_name(self):
        if self.company_id:
            common_name = "AFIP WS %s - %s" % (self.type, self.company_id.name)
            self.common_name = common_name[:50]

    @api.depends("company_cuit", "service_provider_cuit", "service_type")
    def _compute_cuit(self):
        for rec in self:
            if rec.service_type == "outsourced":
                rec.cuit = rec.service_provider_cuit
            else:
                rec.cuit = rec.company_cuit

    @api.onchange("company_id")
    def change_company_id(self):
        if self.company_id:
            self.country_id = self.company_id.country_id.id
            self.state_id = self.company_id.state_id.id
            self.city = self.company_id.city
            self.company_cuit = self.company_id.vat

    def action_confirm(self):
        if not self.key:
            self.generate_key()
        self.write({"state": "confirmed"})
        return True

    def generate_key(self, key_length=2048):
        """Generates a private key with pyafipws"""
        for rec in self:
            k = crypto.PKey()
            k.generate_key(crypto.TYPE_RSA, key_length)
            pem_bytes = crypto.dump_privatekey(crypto.FILETYPE_PEM, k)
            rec.key = pem_bytes.decode("utf-8") if isinstance(pem_bytes, bytes) else pem_bytes

    def action_to_draft(self):
        self.write({"state": "draft"})
        return True

    def action_cancel(self):
        self.write({"state": "cancel"})
        self.certificate_ids.write({"state": "cancel"})
        return True

    def action_create_certificate_request(self):
        """Generates a certificate request to ask AFIP for the certificate"""
        for record in self:
            req = crypto.X509Req()
            req.get_subject().C = self.country_id.code
            if self.state_id:
                req.get_subject().ST = self.state_id.name
            req.get_subject().L = self.city
            req.get_subject().O = self.company_id.name  # noqa: E741
            req.get_subject().OU = self.department
            req.get_subject().CN = self.common_name
            req.get_subject().serialNumber = "CUIT %s" % self.cuit
            k = crypto.load_privatekey(crypto.FILETYPE_PEM, self.key)
            pem_bytes = crypto.dump_privatekey(crypto.FILETYPE_PEM, k)
            self.key = pem_bytes.decode("utf-8") if isinstance(pem_bytes, bytes) else pem_bytes
            req.set_pubkey(k)
            req.sign(k, "sha256")
            csr_bytes = crypto.dump_certificate_request(crypto.FILETYPE_PEM, req)
            csr = csr_bytes.decode("utf-8") if isinstance(csr_bytes, bytes) else csr_bytes
            vals = {
                "csr": csr,
                "alias_id": record.id,
            }
            self.certificate_ids.create(vals)
        return True

    @api.constrains("common_name")
    def check_common_name_len(self):
        if self.filtered(lambda x: x.common_name and len(x.common_name) > 50):
            raise ValidationError(
                _("The Common Name must be lower than 50 characters long")
            )
