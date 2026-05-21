import asyncpg


async def get_product_by_id(
    connection: asyncpg.Connection,
    product_id: int,
) -> asyncpg.Record | None:
    return await connection.fetchrow(
        """
        SELECT product_id, stock, description
        FROM products
        WHERE product_id = $1
        """,
        product_id,
    )


async def reset_stock(
    connection: asyncpg.Connection,
    product_id: int,
    stock: int,
) -> asyncpg.Record | None:
    return await connection.fetchrow(
        """
        UPDATE products
        SET stock = $1
        WHERE product_id = $2
        RETURNING product_id, stock, description
        """,
        stock,
        product_id,
    )


async def decrement_stock_if_available(
    connection: asyncpg.Connection,
    product_id: int,
    purchased_count: int,
) -> int | None:
    return await connection.fetchval(
        """
        UPDATE products
        SET stock = stock - $1
        WHERE product_id = $2
          AND stock >= $1
        RETURNING product_id
        """,
        purchased_count,
        product_id,
    )


async def product_exists(connection: asyncpg.Connection, product_id: int) -> bool:
    return bool(
        await connection.fetchval(
            "SELECT EXISTS(SELECT 1 FROM products WHERE product_id = $1)",
            product_id,
        )
    )
