# Copyright 2018 Eficent <http://www.eficent.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from openupgradelib import openupgrade

_column_renames = {
    'ir_attachment': [
        ('priority', None),
    ],
    'stock_move': [
        ('quantity_done_store', None),
    ],
}


def compute_done_move(cr):
    openupgrade.logger.debug("Computation of done_move in stock_move_line")
    cr.execute(
        """
        ALTER TABLE stock_move_line ADD COLUMN done_move boolean;
        """
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE stock_move_line AS to_update_sml
        SET done_move = sm.is_done
        FROM stock_move AS sm
        WHERE sm.id = to_update_sml.move_id;        
        """
    )


@openupgrade.migrate(use_env=False)
def migrate(cr, version):
    compute_done_move(cr)
    openupgrade.rename_columns(cr, _column_renames)
