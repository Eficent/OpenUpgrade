# Copyright 2018 Eficent <http://www.eficent.com>
# Copyright 2019 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from openupgradelib import openupgrade
from psycopg2.extensions import AsIs


def fill_mass_mailing_list_contact_rel_data(cr):
    openupgrade.logged_query(
        cr, """
        UPDATE mail_mass_mailing_contact_list_rel mmmclr
        SET unsubscription_date = mmmc.%s,
            opt_out = mmmc.%s
        FROM mail_mass_mailing_contact mmmc
        WHERE mmmclr.contact_id = mmmc.id
        """, (
            AsIs(openupgrade.get_legacy_name('unsubscription_date')),
            AsIs(openupgrade.get_legacy_name('opt_out')),
        ),
    )


def fill_mass_mailing_user_id(cr):
    openupgrade.logged_query(
        cr, """
        UPDATE mail_mass_mailing
        SET user_id = create_uid
        WHERE user_id IS NULL""",
    )


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    fill_mass_mailing_list_contact_rel_data(cr)
    fill_mass_mailing_user_id(cr)
