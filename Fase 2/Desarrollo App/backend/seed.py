# backend/seed.py
import asyncio
import uuid

from app.db.session import SessionLocal
from app.models import BotAgent, Tenant, User
from app.core.security import hash_password


async def seed():
    async with SessionLocal() as db:
        # 1. Crear empresa demo
        t = Tenant(
            id=uuid.uuid4(),
            name='Empresa Demo',
            slug='demo',
            legal_name='Demo SpA',
            tax_id='12345678-9',
            country='CL',
            language='es',
            status='active',
            languages=['es'],
            token_limit_month=100000,
            deepseek_key_status='valid',
            deepseek_key_masked='sk-demo***abc'
        )
        db.add(t)
        await db.flush()

        # 2. Crear usuarios
        usuarios = [
            User(tenant_id=None, name='Admin Global', email='adminglobal@allox.ai',
                 password_hash=hash_password('Admin123'), role='platform_admin', lang='es', status='active'),
            User(tenant_id=t.id, name='Admin Empresa', email='adminempresa@demo.com',
                 password_hash=hash_password('Admin123'), role='company_admin', lang='es', status='active'),
            User(tenant_id=t.id, name='Trabajador Consola', email='trabajadorconsola@demo.com',
                 password_hash=hash_password('Admin123'), role='human_agent', lang='es',
                 status='active', escalation_type='both', channel='web', presence='available'),
        ]
        for u in usuarios:
            db.add(u)

        # 3. Crear agentes del bot
        db.add(BotAgent(tenant_id=t.id, agent_type='technical', enabled=True,
                        display_name='Soporte Tecnico Demo',
                        system_prompt='Eres el soporte tecnico de Empresa Demo.'))
        db.add(BotAgent(tenant_id=t.id, agent_type='commercial', enabled=False,
                        display_name='Soporte Comercial Demo',
                        system_prompt='Eres el soporte comercial de Empresa Demo.'))

        await db.commit()
        print('=== DATOS CREADOS ===')
        print('Global:   adminglobal@allox.ai / Admin123')
        print('Empresa:  adminempresa@demo.com / Admin123')
        print('Consola:  trabajadorconsola@demo.com / Admin123')
        print('=====================')


if __name__ == '__main__':
    asyncio.run(seed())