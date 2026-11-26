"""Gateway pembayaran. Saat ini DEMO (konfirmasi manual lewat tombol).

Untuk gateway asli (QRIS/VA/e-wallet): buat class baru dengan method create(),
lalu panggil db.confirm_deposit(deposit_id) dari webhook / polling saat pembayaran sukses.
"""
import random
import string


class DemoGateway:
    name = "DEMO"
    demo = True

    async def create(self, deposit_id: int, amount: int) -> dict:
        ref = "DEMO-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        return {"ref": ref, "instructions": "Mode demo: tekan tombol <b>Bayar (Demo)</b> untuk simulasi pembayaran sukses."}


gateway = DemoGateway()
