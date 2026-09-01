"""
Recette python-for-android pour MarkupSafe.

Pourquoi elle est nécessaire :
MarkupSafe est le seul paquet compilé de la chaîne de dépendances de Flask
(il embarque l'extension C `markupsafe._speedups`). python-for-android n'a pas
de recette pour lui et tente donc de l'installer via pip avec la contrainte
`--only-binary=:all: --platform=android_21_arm64_v8a`. Comme PyPI ne publie
aucun wheel Android pour MarkupSafe, la résolution échoue avec :

    ERROR: No matching distribution found for markupsafe

Cette recette le fait construire depuis les sources avec la chaîne de
compilation croisée du NDK. Le setup.py de MarkupSafe tolère l'échec de
l'extension C et bascule automatiquement sur l'implémentation pure Python,
donc la construction aboutit dans les deux cas.
"""

from pythonforandroid.recipe import PyProjectRecipe


class MarkupSafeRecipe(PyProjectRecipe):
    version = '3.0.3'
    url = 'https://github.com/pallets/markupsafe/archive/{version}.zip'
    depends = ['setuptools']
    site_packages_name = 'markupsafe'


recipe = MarkupSafeRecipe()
