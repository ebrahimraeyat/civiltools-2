import comtypes.client
etabs = comtypes.client.GetActiveObject('CSI.ETABS.API.ETABSObject')
SapModel = etabs.SapModel
ret = SapModel.DatabaseTables.GetAllTables()
for t in ret[1]:
    if 'shear' in str(t).lower() or 'column' in str(t).lower():
        print(t)
