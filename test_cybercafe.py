import unittest
import os
import sys
import json
from datetime import datetime, timedelta

# Ensure cybercafe_manager directory is in the import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'cybercafe_manager'))

import app as db

class CybercafeTestCase(unittest.TestCase):
    def setUp(self):
        # Configure a test database
        db.DB_PATH = 'test_cybercafe.db'
        db.init_db()
        
        # Flask test client
        self.app = db.app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def tearDown(self):
        # Delete test database
        if os.path.exists('test_cybercafe.db'):
            os.remove('test_cybercafe.db')

    def test_database_initialization(self):
        """Test database tables and default data are created successfully"""
        terminals = db.get_all_terminals()
        # Database should start completely empty of default terminals!
        self.assertEqual(len(terminals), 0)

        settings = db.get_settings()
        self.assertEqual(settings['cyber_name'], 'DEK-DRIVSIM CyberCafe')
        self.assertEqual(settings['wifi_ssid'], 'DEK-DRIVSIM_WiFi')

    def test_ticket_generation_and_validation(self):
        """Test generating tickets and retrieving them"""
        # Generate 3 tickets
        tickets = db.generate_tickets(count=3, duration_mins=120, price=1000)
        self.assertEqual(len(tickets), 3)
        self.assertEqual(tickets[0]['duration_mins'], 120)
        self.assertEqual(tickets[0]['price'], 1000)

        # Retrieve all active tickets (should be exactly 3 since no default ones exist!)
        active_tickets = db.get_tickets(status='active')
        self.assertEqual(len(active_tickets), 3)

        # Find ticket by code
        code = tickets[0]['code']
        tck = db.get_ticket_by_code(code)
        self.assertIsNotNone(tck)
        self.assertEqual(tck['status'], 'active')

    def test_player_creation_and_recharging(self):
        """Test player creation, balance inquiry and recharging"""
        username = "TestGamer"
        pwd = "testpassword"
        
        # Create Player
        success = db.create_player(username, pwd, initial_balance=500)
        self.assertTrue(success)
        
        # Duplicate check
        dup_success = db.create_player(username, pwd)
        self.assertFalse(dup_success)

        # Get Player
        player = db.get_player_by_username(username)
        self.assertIsNotNone(player)
        self.assertEqual(player['balance'], 500)

        # Recharge Player
        recharge_success = db.recharge_player(player['id'], 1500)
        self.assertTrue(recharge_success)
        
        player_updated = db.get_player_by_username(username)
        self.assertEqual(player_updated['balance'], 2000)

    def test_session_management_flow(self):
        """Test complete session lifecycle (start, pause, resume, stop)"""
        # 1. Register a terminal first on-the-fly!
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO terminals (name, type) VALUES ('PC-01', 'PC')")
        conn.commit()
        conn.close()
        
        terminal = db.get_terminal_by_name('PC-01')
        self.assertIsNotNone(terminal)
        
        # 2. Generate a ticket to use
        tickets = db.generate_tickets(count=1, duration_mins=60, price=500)
        tck_code = tickets[0]['code']
        
        # 3. Start a session with a Ticket
        success, session_id = db.start_ticket_session(terminal['id'], tck_code)
        self.assertTrue(success)
        self.assertIsInstance(session_id, int)
        
        # Verify terminal status is updated
        term_updated = db.get_terminal(terminal['id'])
        self.assertEqual(term_updated['status'], 'occupied')
        self.assertEqual(term_updated['session_type'], 'ticket')
        
        # Verify ticket status is updated to used
        tck_updated = db.get_ticket_by_code(tck_code)
        self.assertEqual(tck_updated['status'], 'used')

        # 4. Pause the session
        success, msg = db.pause_session(terminal['id'])
        self.assertTrue(success)
        
        term_paused = db.get_terminal(terminal['id'])
        self.assertEqual(term_paused['status'], 'paused')

        # 5. Resume the session
        success, msg = db.resume_session(terminal['id'])
        self.assertTrue(success)
        
        term_resumed = db.get_terminal(terminal['id'])
        self.assertEqual(term_resumed['status'], 'occupied')

        # 6. Stop the session
        success, msg = db.stop_session(terminal['id'])
        self.assertTrue(success)
        
        term_stopped = db.get_terminal(terminal['id'])
        self.assertEqual(term_stopped['status'], 'free')
        self.assertIsNone(term_stopped['current_session_id'])

    def test_financials_and_transactions(self):
        """Verify transaction records and daily summaries function"""
        # Register terminal
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO terminals (name, type) VALUES ('PC-02', 'PC')")
        conn.commit()
        conn.close()
        terminal = db.get_terminal_by_name('PC-02')

        # Fetch initial stats
        initial_summary = db.get_financial_summary()
        initial_revenue = initial_summary['today_revenue']

        # Generate ticket and sell (which records 1200 CFA sale)
        tickets = db.generate_tickets(count=1, duration_mins=180, price=1200)
        db.start_ticket_session(terminal['id'], tickets[0]['code'])

        # Check updated financials
        updated_summary = db.get_financial_summary()
        self.assertEqual(updated_summary['today_revenue'], initial_revenue + 1200)
        self.assertGreater(len(updated_summary['recent_transactions']), 0)
        self.assertEqual(updated_summary['recent_transactions'][0]['amount'], 1200)

if __name__ == '__main__':
    unittest.main()
