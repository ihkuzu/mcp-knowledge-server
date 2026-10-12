# Order Status Glossary

This page explains the status values in the order system and the analytics replica.

## delivered

The carrier confirmed delivery. Most orders end in this status. Partial returns do not change it.

## cancelled

The order was cancelled before shipping, by the customer, by support or automatically, for example because of a foreign delivery address or a failed payment. Cancelled orders do not count as revenue.

## returned

All items of the order came back to the warehouse and the refund was started. Returned orders do not count as revenue either.

## Revenue in reports

Revenue is the sum of quantity times product price over order items of orders with status `delivered`. Prices in the analytics replica are current list prices, so historical revenue is an approximation when prices changed.

## Tables

The analytics replica has the tables customers, products, orders and order_items. An order has one or more order items, each with a product and a quantity.
