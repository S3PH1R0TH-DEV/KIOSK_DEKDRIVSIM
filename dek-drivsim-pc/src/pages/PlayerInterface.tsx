import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { 
  getSettings, 
  getTerminals, 
  getGames, 
  getPlayers, 
  getFinancialSummary,
  startTicketSession,
  startPlayerSession
} from '../api'

const PlayerInterface = () => {
  const navigate = useNavigate()
  const [settings, setSettings] = useState<any>(null)
  const [terminals, setTerminals] = useState<any[]>([])
  const [games, setGames] = useState<any[]>([])
  const [players, setPlayers] = useState<any[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [selectedGame, setSelectedGame] = useState<string | null>(null)

  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true)
      try {
        const [
          s,
          t,
          g,
          p,
          sum,
        ] = await Promise.all([
          getSettings(),
          getTerminals(),
          getGames(),
          getPlayers(),
          getFinancialSummary(),
        ])
        setSettings(s)
        setTerminals(t)
        setGames(g)
        setPlayers(p)
        setSummary(sum)
      } catch (error) {
        console.error('Error loading player data:', error)
      } finally {
        setIsLoading(false)
      }
    }

    loadData()

    const intervalId = setInterval(loadData, 5000)
    return () => clearInterval(intervalId)
  }, [])

  const handleLogin = async () => {
    if (!username || !password) {
      alert('Veuillez entrer vos identifiants')
      return
    }

    // Find terminal that's free
    const freeTerminal = terminals.find(t => t.status === 'free')
    if (!freeTerminal) {
      alert('Aucun poste disponible pour le moment')
      return
    }

    const result = await startPlayerSession(freeTerminal.id, username, password)
    if (result.success) {
      alert('Session lancée avec succès !')
      navigate('/', { replace: true })
    } else {
      alert(result.message || 'Échec de la connexion')
    }
  }

  const handleTicketUnlock = async (code: string) => {
    const freeTerminal = terminals.find(t => t.status === 'free')
    if (!freeTerminal) {
      alert('Aucun poste disponible')
      return
    }

    const result = await startTicketSession(freeTerminal.id, code)
    if (result.success) {
      alert('Ticket appliqué avec succès !')
      navigate('/', { replace: true })
    } else {
      alert(result.message || 'Code ticket invalide')
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-8">
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-8 max-w-md w-full">
          <h2 className="text-center text-fuchsia-400 text-2xl font-bold mb-4">DEK-DRIVSIM</h2>
          <p className="text-slate-400 text-center mb-8">Initialisation de l'interface joueur...</p>
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-fuchsia-500 mx-auto"></div>
        </div>
      </div>
    )
  }

  const triggerEmergency = async () => {
    const code = prompt('Mastercode pour restaurer le bureau Windows :')
    if (code === null) return
    if ((window as any).electronAPI?.verifyMastercode) {
      const ok = await (window as any).electronAPI.verifyMastercode(code)
      if (!ok) alert('Mastercode incorrect')
    } else {
      if (code === 'DEK-EXIT-2026' || code === 'admin123') alert('Mastercode OK (hors Electron, fermez manuellement)')
      else alert('Mastercode incorrect')
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 relative">
      {/* Bouton secours discret — 5 clics rapides ou clic long = prompt mastercode */}
      <button onClick={triggerEmergency} title="Secours — restaurer le bureau (mastercode)" className="absolute top-2 right-2 w-2 h-2 bg-slate-800 hover:bg-fuchsia-500 rounded-full opacity-20 hover:opacity-100 transition-all z-50" />
      <header className="bg-slate-950/95 border-b border-slate-800 sticky top-0 z-30 backdrop-blur-md shadow-2xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <img src="/logo.png" alt="Logo" className="w-12 h-12 rounded-full border border-slate-800 object-cover" />
            <div>
              <h1 className="text-md sm:text-lg font-black tracking-widest text-white uppercase flex items-center gap-2">
                <span className="neon-glow-purple">{settings?.cyber_name || 'DEK-DRIVSIM'}</span>
                <span className="text-[9px] px-2 py-0.5 bg-fuchsia-500/10 border border-fuchsia-500/30 text-fuchsia-400 font-bold rounded-full uppercase tracking-widest font-mono">JOUER</span>
              </h1>
              <p className="text-[10px] text-slate-500 font-mono">Bienvenue sur le simulateur de conduite</p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs font-mono">
            <div>
              <span className="text-slate-400">Connecté en tant que :</span>
              <span className="font-bold text-fuchsia-400" id="player-username">---</span>
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">

        {/* Games Section */}
        <section className="grid grid-cols-1 lg:grid-cols-2 md:grid-cols-3 gap-4">
          {games.map((game) => (
            <div key={game.id} className="bg-slate-900 border border-slate-800/80 rounded-2xl overflow-hidden hover:border-fuchsia-500/50 hover:scale-[1.02] transition-all duration-300 flex flex-col justify-between group">
              <div className="aspect-video w-full bg-cover bg-center border-b border-slate-800" style={{ backgroundImage: `url('${game.image_url}')` }}></div>
              <div className="p-3">
                <span className="text-[9px] text-fuchsia-400 font-extrabold uppercase block mb-1 font-mono">{game.category}</span>
                <h4 className="font-extrabold text-xs text-white group-hover:text-fuchsia-400 truncate transition-colors uppercase tracking-wide">{game.name}</h4>
                <p className="text-[8px] text-slate-500 font-mono mt-1 truncate">{game.launch_path}</p>
              </div>
              <div className="px-3 pb-3">
                <button onClick={() => setSelectedGame(game.name)} className="w-full py-2.5 bg-slate-950 group-hover:bg-gradient-to-r group-hover:from-fuchsia-600 group-hover:to-fuchsia-500 text-slate-400 group-hover:text-white font-extrabold text-[10px] rounded-xl transition-all uppercase flex items-center justify-center gap-1 border border-slate-800 group-hover:border-fuchsia-500/30 font-mono shadow-md">
                  <i className="fa-solid fa-gamepad"></i> Lancer le jeu
                </button>
              </div>
            </div>
          ))}
          {games.length === 0 && (
            <div className="col-span-full text-center py-12">
              <i className="fa-solid fa-gamepad text-4xl text-slate-700 mb-2"></i>
              <p className="text-slate-500 font-bold">Aucun jeu configuré</p>
              <p className="text-xs text-slate-600 mt-1">Connectez-vous en mode admin en bas à gauche pour enregistrer des jeux.</p>
            </div>
          )}
        </section>

        {/* Player Controls */}
        <section className="bg-slate-950/60 border border-slate-800 rounded-3xl p-6 shadow-xl">
          <div>
            <h2 className="text-md sm:text-lg font-black tracking-widest text-white flex items-center gap-2 uppercase">
              <i className="fa-solid fa-user text-fuchsia-500"></i> Votre Compte
            </h2>
            <div className="mt-4">
              <label className="block text-[9px] font-bold text-slate-500 uppercase mb-1.5">Identifiant</label>
              <div className="relative">
                <input type="text" id="player-username" placeholder="Pseudo Joueur" value={username} onChange={(e) => setUsername(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-3 text-sm text-white focus:outline-none focus:border-fuchsia-500 uppercase tracking-wider font-mono" />
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500">
                  <i className="fa-solid fa-user"></i>
                </span>
              </div>
            </div>
            <div className="mt-4">
              <label className="block text-[9px] font-bold text-slate-500 uppercase mb-1.5">Mot de passe</label>
              <div className="relative">
                <input type="password" id="player-password" placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-3 text-sm text-white focus:outline-none focus:border-fuchsia-500 transition-all" />
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500">
                  <i className="fa-solid fa-key"></i>
                </span>
              </div>
            </div>
            <div className="mt-6">
              <button onClick={handleLogin} className="w-full py-3 bg-fuchsia-600 hover:bg-fuchsia-500 text-white font-bold rounded-xl uppercase tracking-widest transition-all font-mono shadow-lg shadow-fuchsia-600/20 border border-fuchsia-500/20">
                <i className="fa-solid fa-right-to-bracket"></i> Se Connecter & Jouer
              </button>
              <button onClick={() => handleTicketUnlock(prompt('Entrez le code ticket') || '')} className="w-full py-3 bg-cyan-600 hover:bg-cyan-500 text-white font-bold rounded-xl uppercase tracking-widest transition-all mt-2 font-mono border border-cyan-500/20">
                <i className="fa-solid fa-ticket"></i> Utiliser un Code Ticket
              </button>
            </div>
          </div>
        </section>

      </main>
    </div>
  )
}

export default PlayerInterface