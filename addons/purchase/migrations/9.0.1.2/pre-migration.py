# -*- coding: utf-8 -*-
# © 2015 Eficent Business and IT Consulting Services S.L. -
# Jordi Ballester Alomar
# © 2015 Serpent Consulting Services Pvt. Ltd. - Sudhir Arya
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from openupgradelib import openupgrade

column_copies = {
    'purchase_order': [
        ('state', None, None),
    ],
}


def map_order_state(cr):
    """ Map values for state field in purchase.order and purchase.order.line.
    Do this in the pre script because it influences the automatic calculation
    of the computed fields wrt. invoicing """
    openupgrade.map_values(
        cr, openupgrade.get_legacy_name('state'), 'state',
        [('approved', 'purchase'), ('bid', 'sent'),
         ('confirmed', 'to approve'), ('draft', 'draft'),
         ('except_invoice', 'purchase'), ('except_picking', 'purchase')],
        table='purchase_order')

    cr.execute("""
        UPDATE purchase_order_line l
        SET state = o.state
        FROM purchase_order o
        WHERE l.order_id = o.id""")


def pre_create_po_double_validation(cr, env):
    """ In v8 when you install the module 'purchase_double_validation'
    the po workflow is altered to put conditions to change the po status to
    waiting approval if a condition is met. In v9 this is handled without
    workflow."""

    cr.execute("""SELECT column_name
    FROM information_schema.columns
    WHERE table_name='res_company' AND
    column_name='po_double_validation'""")

    if not cr.fetchone():
        cr.execute(
            """
            ALTER TABLE res_company ADD COLUMN po_double_validation
            boolean;
            COMMENT ON COLUMN res_company.po_double_validation IS
            'Levels of Approvals';
            """)

    cr.execute("""SELECT column_name
    FROM information_schema.columns
    WHERE table_name='res_company' AND
    column_name='po_double_validation_amount'""")

    if not cr.fetchone():
        cr.execute(
            """
            ALTER TABLE res_company ADD COLUMN po_double_validation_amount
            float;
            COMMENT ON COLUMN res_company.po_double_validation_amount IS
            'Double validation amount';
            """)

    double_validation_transition = env.ref(
        'purchase_double_validation.trans_confirmed_double_gt')
    po_double_validation_amount = 5000.0
    if double_validation_transition:
        po_double_validation = 'two_step'
        condition = False
        if double_validation_transition.condition.find('>=') >= 0:
            condition = '>='
        elif double_validation_transition.condition.find('>=') >= 0:
            condition = '<'
        if condition:
            po_double_validation_amount = (
                double_validation_transition.condition.split(condition, 1)[1])
    else:
        po_double_validation = 'one_step'

    cr.execute("""
        UPDATE res_company
        SET po_double_validation = %s,
            po_double_validation_amount = %s
    """ % (po_double_validation, po_double_validation_amount))


@openupgrade.migrate(use_env=True)
def migrate(env, version):
    cr = env.cr
    openupgrade.copy_columns(cr, column_copies)
    map_order_state(cr)
    pre_create_po_double_validation(cr, env)
