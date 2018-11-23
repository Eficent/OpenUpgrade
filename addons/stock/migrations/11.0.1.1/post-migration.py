# -*- coding: utf-8 -*-
# Copyright 2017-2018 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from openupgradelib import openupgrade
from psycopg2.extensions import AsIs


@openupgrade.logging()
def compute_stock_move_reference(env):
    """Compute through SQL this field for saving time."""
    openupgrade.logged_query(
        env.cr, """
        UPDATE stock_move
        SET reference = name
        WHERE picking_id IS NULL"""
    )
    openupgrade.logged_query(
        env.cr, """
        UPDATE stock_move sm
        SET reference = sp.name
        FROM stock_picking sp
        WHERE sm.picking_id = sp.id"""
    )


@openupgrade.logging()
def compute_picking_scheduled_date(env):
    """Compute through SQL this field for saving time."""
    openupgrade.logged_query(
        env.cr, """
        UPDATE stock_picking sp
        SET scheduled_date = sub.date_expected
        FROM (
            SELECT sm.picking_id,
                CASE WHEN sp.move_type = 'direct'
                THEN MIN(sm.date_expected)
                ELSE MAX(sm.date_expected)
                END AS date_expected
            FROM stock_move sm, stock_picking sp
            WHERE sm.picking_id = sp.id
            GROUP BY sm.picking_id, sp.move_type
        ) AS sub
        WHERE sub.picking_id = sp.id"""
    )


@openupgrade.logging()
def product_assign_responsible(env):
    """Assign as responsible the creator of the product."""
    openupgrade.logged_query(
        env.cr, """
        UPDATE product_template
        SET responsible_id = create_uid
        """
    )


@openupgrade.logging()
def create_specific_procurement_rules_from_globals(env):
    """Create one record per route for the global rules found in previous
    version.
    """
    for table in ['procurement_rule', 'stock_location_path']:
        env.cr.execute(
            """SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
                AND column_name != 'id'
            ORDER BY ordinal_position""",
            (table, ),
        )
        dest_columns = [x[0] for x in env.cr.fetchall()]
        src_columns = [
            ('t.' + x) if x != 'route_id' else 'slr.id' for x in dest_columns
        ]
        openupgrade.logged_query(
            env.cr, """
            INSERT INTO %s
            (%s)
            SELECT %s
            FROM %s t, stock_location_route slr""", (
                AsIs(table),
                AsIs(", ".join(dest_columns)),
                AsIs(", ".join(src_columns)),
                AsIs(openupgrade.get_legacy_name(table)),
            ),
        )


@openupgrade.logging()
def set_quant_reserved_qty(env):
    """If there was a reserved move, then the entire quantity was reserved,
    so we have to put quant qty as the reserved qty. Later on end migration,
    merge operation will sum all the reserved ones.
    """
    openupgrade.logged_query(
        env.cr, """
        UPDATE stock_quant
        SET reserved_quantity = quantity
        WHERE reservation_id IS NOT NULL""",
    )


@openupgrade.logging()
def set_partially_available_state(env):
    openupgrade.logged_query(
        env.cr, """
        UPDATE stock_move
        SET state = 'partially_available'
        WHERE partially_available AND state != 'done'"""
    )


@openupgrade.logging()
def create_stock_move_line(env):
    """This method creates stock.move.line recreated from old
    stock.pack.operation records. These records are created only for done
    moves, as for those not done, there's no need of creating stock.move.line
    or it's handled later:

    * For outgoing or internal transfers without reserved quantity, clicking on
      "Check availability" will work.
    * For outgoing or internal transfers with reserved quantity,
      stock.move.line records are created from other source (quants) later
      in `create_stock_move_line_reserved` method.
    * For incoming transfers, clicking on validate for accepting full
      quantities, or writing the quantity in the lines you want in
      "Operations" tab. The only drawback is that if you want to use the
      detailed operation mode, you will have to enter quantity manually.
    """
    insert_into = """create_date,
            create_uid,
            date,
            location_dest_id,
            location_id,
            lot_id,
            lot_name,
            move_id,
            ordered_qty,
            owner_id,
            package_id,
            picking_id,
            product_id,
            product_qty,
            product_uom_id,
            product_uom_qty,
            qty_done,
            reference,
            state,
            result_package_id,
            write_date,
            write_uid"""
    select = """MIN(spo.create_date),
            MIN(spo.create_uid),
            MIN(spo.date),
            MIN(spo.location_dest_id),
            MIN(spo.location_id),
            sq.lot_id,
            MIN(spl.name),
            MIN(sm.id),
            SUM(smol.qty),
            spo.owner_id,
            spo.package_id,
            spo.picking_id,
            spo.product_id,
            SUM(smol.qty),
            MIN(spo.product_uom_id),
            SUM(smol.qty),
            SUM(smol.qty),
            MIN(COALESCE(sp.name, sm.name)),
            'done',
            spo.result_package_id,
            MIN(spo.write_date),
            MIN(spo.write_uid)"""
    from_ = """stock_pack_operation spo
            INNER JOIN stock_move_operation_link smol
                ON smol.operation_id = spo.id
            INNER JOIN stock_move sm ON sm.id = smol.move_id
            INNER JOIN product_product pp ON spo.product_id = pp.id
            LEFT JOIN stock_picking sp ON sp.id = spo.picking_id
            LEFT JOIN stock_quant sq ON sq.id = smol.reserved_quant_id
            LEFT JOIN stock_production_lot spl ON spl.id = sq.lot_id"""
    openupgrade.logged_query(
        env.cr, """
        INSERT INTO stock_move_line (%(insert_into)s
        )
        SELECT %(select)s
        FROM %(from)s
        WHERE sm.state = 'done'
        GROUP BY sq.lot_id, spo.product_id, spo.owner_id, spo.package_id,
            spo.result_package_id, spo.picking_id""" % {
            'insert_into': insert_into,
            'select': select,
            'from': from_,
        },
    )


@openupgrade.logging()
def create_stock_move_line_reserved(env):
    """This method creates stock.move.line got from old stock.quant
    reservation_id field for recreating partially available moves.
    """
    insert_into = """create_date,
            create_uid,
            date,
            location_dest_id,
            location_id,
            lot_id,
            lot_name,
            move_id,
            ordered_qty,
            owner_id,
            package_id,
            picking_id,
            product_id,
            product_qty,
            product_uom_id,
            product_uom_qty,
            qty_done,
            reference,
            state,
            write_date,
            write_uid"""
    select = """current_timestamp,
            MIN(sq.write_uid),
            sm.date::date,
            sm.location_dest_id,
            sm.location_id,
            sq.lot_id,
            MIN(spl.name),
            sm.id,
            LEAST(SUM(sq.quantity), sm.product_uom_qty),
            sq.owner_id,
            sq.package_id,
            sm.picking_id,
            sq.product_id,
            LEAST(SUM(sq.quantity), sm.product_uom_qty),
            sm.product_uom,
            LEAST(SUM(sq.quantity), sm.product_uom_qty),
            0,
            MIN(COALESCE(sp.name, sm.name)),
            sm.state,
            current_timestamp,
            MIN(sq.write_uid)"""
    from_ = """stock_quant sq
            INNER JOIN stock_move sm ON sm.id = sq.reservation_id
            LEFT JOIN stock_picking sp ON sp.id = sm.picking_id
            LEFT JOIN stock_production_lot spl ON spl.id = sq.lot_id"""
    openupgrade.logged_query(
        env.cr, """
        INSERT INTO stock_move_line (%(insert_into)s
        )
        SELECT %(select)s
        FROM %(from)s
        GROUP BY sq.lot_id, sq.product_id, sq.owner_id, sq.package_id,
            sm.id""" % {
            'insert_into': insert_into,
            'select': select,
            'from': from_,
        },
    )


def recompute_stock_move_line_qty_different_uom(env):
    """Re-compute product_qty for those lines where product UoM != line UoM."""
    env.cr.execute(
        """SELECT sml.id
        FROM stock_move_line sml
            INNER JOIN product_product pp ON pp.id = sml.product_id
            INNER JOIN product_template pt ON pt.id = pp.product_tmpl_id
        WHERE pt.uom_id != sml.product_uom_id"""
    )
    lines = env['stock.move.line'].browse([x[0] for x in env.cr.fetchall()])
    for line in lines:
        product_qty = line.product_uom_id._compute_quantity(
            line.product_uom_qty, line.product_id.uom_id,
            rounding_method='HALF-UP',
        )
        # Can't assign by ORM, so by SQL
        env.cr.execute(
            "UPDATE stock_move_line SET product_qty = %s WHERE id = %s",
            (product_qty, line.id),
        )


def fill_stock_move_line_consume_rel(cr):
    openupgrade.logged_query(
        cr,
        """
        INSERT INTO stock_move_line_consume_rel (consume_line_id,
            produce_line_id)
        SELECT DISTINCT sml1.id, sml2.id
        FROM stock_quant_consume_rel sqcr
        INNER JOIN stock_quant_move_rel sqmr1
            ON sqmr1.quant_id = sqcr.consume_quant_id
        INNER JOIN stock_quant_move_rel sqmr2
            ON sqmr2.quant_id = sqcr.produce_quant_id
        INNER JOIN stock_move_line sml1
            ON sml1.move_id = sqmr1.move_id
        INNER JOIN stock_move_line sml2
            ON sml2.move_id = sqmr2.move_id
        """
    )


@openupgrade.migrate(use_env=True)
def migrate(env, version):
    compute_stock_move_reference(env)
    compute_picking_scheduled_date(env)
    product_assign_responsible(env)
    create_specific_procurement_rules_from_globals(env)
    set_quant_reserved_qty(env)
    openupgrade.m2o_to_x2m(
        env.cr, env['stock.move'], 'stock_move', 'move_dest_ids',
        'move_dest_id',
    )
    # TODO: Get is_initial_demand_editable, is_locked values in stock.move
    set_partially_available_state(env)
    create_stock_move_line(env)
    create_stock_move_line_reserved(env)
    recompute_stock_move_line_qty_different_uom(env)
    if openupgrade.table_exists(env.cr, 'stock_quant_consume_rel'):
        fill_stock_move_line_consume_rel(env.cr)
