import types
import time
from pandac.PandaModules import *
from direct.distributed.ClockDelta import *
from direct.gui.DirectGui import *
from pandac.PandaModules import *
from direct.interval.IntervalGlobal import ivalMgr
from direct.directnotify import DirectNotifyGlobal
from direct.distributed import DistributedSmoothNode
from direct.distributed.PyDatagram import PyDatagram
from direct.distributed.PyDatagramIterator import PyDatagramIterator
from direct.task import Task
from direct.fsm import ClassicFSM
from direct.fsm import State
from direct.showbase.PythonUtil import Functor, ScratchPad
from direct.showbase.InputStateGlobal import inputState
from otp.avatar import Avatar
from otp.avatar import DistributedAvatar
from otp.friends import FriendManager
from otp.login import TTAccount
from otp.login import AccountServerConstants
from otp.login import LoginScreen
from otp.login import LoginGSAccount
from otp.login import LoginGoAccount
from otp.login import LoginWebPlayTokenAccount
from otp.login import LoginTTAccount
from otp.login import HTTPUtil
from otp.distributed import OTPClientRepository
from otp.distributed import PotentialAvatar
from otp.distributed import PotentialShard
from otp.distributed import DistributedDistrict
from otp.distributed.OtpDoGlobals import *
from otp.distributed import OtpDoGlobals
from otp.otpbase import OTPGlobals
from otp.otpbase import OTPLocalizer
from otp.otpbase import OTPLauncherGlobals
from otp.avatar.Avatar import teleportNotify
from toontown.toonbase.ToonBaseGlobal import *
from toontown.toonbase.ToontownGlobals import *
from toontown.launcher.DownloadForceAcknowledge import *
from toontown.distributed import DelayDelete
from toontown.friends import FriendHandle
from toontown.friends import FriendsListPanel
from toontown.friends import ToontownFriendSecret
from toontown.uberdog import TTSpeedchatRelay
from toontown.login import DateObject
from toontown.login import AccountServerDate
from toontown.login import AvatarChooser
from toontown.makeatoon import MakeAToon
from toontown.pets import DistributedPet, PetDetail, PetHandle
from toontown.toonbase import TTLocalizer
from toontown.toontowngui import TTDialog
from toontown.toon import LocalToon
from toontown.toon import ToonDNA
from toontown.distributed import ToontownDistrictStats
from toontown.makeatoon import TTPickANamePattern
from toontown.parties import ToontownTimeManager
from toontown.toon import Toon, DistributedToon
from ToontownMsgTypes import *
import HoodMgr
import PlayGame
from toontown.toontowngui import ToontownLoadingBlocker
from toontown.hood import StreetSign

class ToontownClientRepository(OTPClientRepository.OTPClientRepository):
    SupportTutorial = 1
    GameGlobalsId = OTP_DO_ID_TOONTOWN
    SetZoneDoneEvent = 'TCRSetZoneDone'
    EmuSetZoneDoneEvent = 'TCREmuSetZoneDone'
    SetInterest = 'Set'
    ClearInterest = 'Clear'
    ClearInterestDoneEvent = 'TCRClearInterestDone'
    KeepSubShardObjects = False
    
    def __init__(self, serverVersion, launcher = None):
        OTPClientRepository.OTPClientRepository.__init__(self, serverVersion, launcher, playGame = PlayGame.PlayGame)
        self._playerAvDclass = self.dclassesByName['DistributedToon']
        setInterfaceFont(TTLocalizer.InterfaceFont)
        setSignFont(TTLocalizer.SignFont)
        setFancyFont(TTLocalizer.FancyFont)
        nameTagFontIndex = 0
        for font in TTLocalizer.NametagFonts:
            setNametagFont(nameTagFontIndex, TTLocalizer.NametagFonts[nameTagFontIndex])
            nameTagFontIndex += 1
        
        self.toons = { }
        if self.http.getVerifySsl() != HTTPClient.VSNoVerify:
            self.http.setVerifySsl(HTTPClient.VSNoDateCheck)

        self._ToontownClientRepository__forbidCheesyEffects = 0
        self.friendManager = None
        self.speedchatRelay = None
        self.trophyManager = None
        self.bankManager = None
        self.catalogManager = None
        self.welcomeValleyManager = None
        self.newsManager = None
        self.streetSign = None
        self.distributedDistrict = None
        self.partyManager = None
        self.inGameNewsMgr = None
        self.whitelistMgr = None
        self.toontownTimeManager = ToontownTimeManager.ToontownTimeManager()
        self.avatarFriendsManager = self.generateGlobalObject(OtpDoGlobals.OTP_DO_ID_AVATAR_FRIENDS_MANAGER, 'AvatarFriendsManager')
        self.playerFriendsManager = self.generateGlobalObject(OtpDoGlobals.OTP_DO_ID_PLAYER_FRIENDS_MANAGER, 'TTPlayerFriendsManager')
        self.speedchatRelay = self.generateGlobalObject(OtpDoGlobals.OTP_DO_ID_TOONTOWN_SPEEDCHAT_RELAY, 'TTSpeedchatRelay')
        self.deliveryManager = self.generateGlobalObject(OtpDoGlobals.OTP_DO_ID_TOONTOWN_DELIVERY_MANAGER, 'DistributedDeliveryManager')
        if config.GetBool('want-code-redemption', 1):
            self.codeRedemptionManager = self.generateGlobalObject(OtpDoGlobals.OTP_DO_ID_TOONTOWN_CODE_REDEMPTION_MANAGER, 'TTCodeRedemptionMgr')
        
        self.streetSign = None
        self.furnitureManager = None
        self.objectManager = None
        self.friendsMap = { }
        self.friendsOnline = { }
        self.friendsMapPending = 0
        self.friendsListError = 0
        self.friendPendingChatSettings = { }
        self.elderFriendsMap = { }
        self._ToontownClientRepository__queryAvatarMap = { }
        self.dateObject = DateObject.DateObject()
        self.accountServerDate = AccountServerDate.AccountServerDate()
        self.hoodMgr = HoodMgr.HoodMgr(self)
        self.setZonesEmulated = 0
        self.old_setzone_interest_handle = None
        self.setZoneQueue = Queue()
        self.accept(ToontownClientRepository.SetZoneDoneEvent, self._handleEmuSetZoneDone)
        self._deletedSubShardDoIds = set()
        self.toonNameDict = { }
        self.gameFSM.addState(State.State('skipTutorialRequest', self.enterSkipTutorialRequest, self.exitSkipTutorialRequest, [
            'playGame',
            'gameOff',
            'tutorialQuestion']))
        state = self.gameFSM.getStateNamed('waitOnEnterResponses')
        state.addTransition('skipTutorialRequest')
        state = self.gameFSM.getStateNamed('playGame')
        state.addTransition('skipTutorialRequest')
        self.wantCogdominiums = base.config.GetBool('want-cogdominiums', 1)
        self.wantEmblems = base.config.GetBool('want-emblems', 0)
        if base.config.GetBool('tt-node-check', 0):
            for species in ToonDNA.toonSpeciesTypes:
                for head in ToonDNA.getHeadList(species):
                    for torso in ToonDNA.toonTorsoTypes:
                        for legs in ToonDNA.toonLegTypes:
                            for gender in ('m', 'f'):
                                print 'species: %s, head: %s, torso: %s, legs: %s, gender: %s' % (species, head, torso, legs, gender)
                                dna = ToonDNA.ToonDNA()
                                dna.newToon((head, torso, legs, gender))
                                toon = Toon.Toon()
                                
                                try:
                                    toon.setDNA(dna)
                                except Exception, e:
                                    print e
                                

                            
                        
                    
                
            
        

    
    def congratulations(self, avatarChoice):
        self.acceptedScreen = loader.loadModel('phase_3/models/gui/toon_council')
        self.acceptedScreen.setScale(0.66700000000000004)
        self.acceptedScreen.reparentTo(aspect2d)
        buttons = loader.loadModel('phase_3/models/gui/dialog_box_buttons_gui')
        self.acceptedBanner = DirectLabel(parent = self.acceptedScreen, relief = None, text = OTPLocalizer.CRNameCongratulations, text_scale = 0.17999999999999999, text_fg = Vec4(0.59999999999999998, 0.10000000000000001, 0.10000000000000001, 1), text_pos = (0, 0.050000000000000003), text_font = getMinnieFont())
        newName = avatarChoice.approvedName
        self.acceptedText = DirectLabel(parent = self.acceptedScreen, relief = None, text = OTPLocalizer.CRNameAccepted % newName, text_scale = 0.125, text_fg = Vec4(0, 0, 0, 1), text_pos = (0, -0.14999999999999999))
        self.okButton = DirectButton(parent = self.acceptedScreen, image = (buttons.find('**/ChtBx_OKBtn_UP'), buttons.find('**/ChtBx_OKBtn_DN'), buttons.find('**/ChtBx_OKBtn_Rllvr')), relief = None, text = 'Ok', scale = 1.5, text_scale = 0.050000000000000003, text_pos = (0.0, -0.10000000000000001), pos = (0, 0, -1), command = self._ToontownClientRepository__handleCongrats, extraArgs = [
            avatarChoice])
        buttons.removeNode()
        base.transitions.noFade()

    
    def _ToontownClientRepository__handleCongrats(self, avatarChoice):
        self.acceptedBanner.destroy()
        self.acceptedText.destroy()
        self.okButton.destroy()
        self.acceptedScreen.removeNode()
        del self.acceptedScreen
        del self.okButton
        del self.acceptedText
        del self.acceptedBanner
        datagram = PyDatagram()
        datagram.addUint16(CLIENT_SET_WISHNAME_CLEAR)
        datagram.addUint32(avatarChoice.id)
        datagram.addUint8(1)
        self.send(datagram)
        self.loginFSM.request('waitForSetAvatarResponse', [
            avatarChoice])

    
    def betterlucknexttime(self, avList, index):
        self.rejectDoneEvent = 'rejectDone'
        self.rejectDialog = TTDialog.TTGlobalDialog(doneEvent = self.rejectDoneEvent, message = TTLocalizer.NameShopNameRejected, style = TTDialog.Acknowledge)
        self.rejectDialog.show()
        self.acceptOnce(self.rejectDoneEvent, self._ToontownClientRepository__handleReject, [
            avList,
            index])
        base.transitions.noFade()

    
    def _ToontownClientRepository__handleReject(self, avList, index):
        self.rejectDialog.cleanup()
        datagram = PyDatagram()
        datagram.addUint16(CLIENT_SET_WISHNAME_CLEAR)
        avid = 0
        for k in avList:
            if k.position == index:
                avid = k.id
                continue
        
        if avid == 0:
            self.notify.error('Avatar rejected not found in avList.  Index is: ' + str(index))
        
        datagram.addUint32(avid)
        datagram.addUint8(0)
        self.send(datagram)
        self.loginFSM.request('waitForAvatarList')

    
    def enterChooseAvatar(self, avList):
        ModelPool.garbageCollect()
        TexturePool.garbageCollect()
        self.sendSetAvatarIdMsg(0)
        self.clearFriendState()
        if self.music == None and base.musicManagerIsValid:
            self.music = base.musicManager.getSound('phase_3/audio/bgm/tt_theme.mid')
            if self.music:
                self.music.setLoop(1)
                self.music.setVolume(0.90000000000000002)
                self.music.play()
            
        
        base.playMusic(self.music, looping = 1, volume = 0.90000000000000002, interrupt = None)
        self.handler = self.handleMessageType
        self.avChoiceDoneEvent = 'avatarChooserDone'
        self.avChoice = AvatarChooser.AvatarChooser(avList, self.loginFSM, self.avChoiceDoneEvent)
        self.avChoice.load(self.isPaid())
        self.avChoice.enter()
        self.accept(self.avChoiceDoneEvent, self._ToontownClientRepository__handleAvatarChooserDone, [
            avList])
        if config.GetBool('want-gib-loader', 1):
            self.loadingBlocker = ToontownLoadingBlocker.ToontownLoadingBlocker(avList)
        

    
    def _ToontownClientRepository__handleAvatarChooserDone(self, avList, doneStatus):
        done = doneStatus['mode']
        if done == 'exit':
            if not launcher.isDummy() and launcher.VISTA:
                if not self.isPaid():
                    self.loginFSM.request('shutdown', [
                        OTPLauncherGlobals.ExitUpsell])
                else:
                    self.loginFSM.request('shutdown')
            else:
                self.loginFSM.request('shutdown')
            return None
        
        index = self.avChoice.getChoice()
        for av in avList:
            if av.position == index:
                avatarChoice = av
                self.notify.info('================')
                self.notify.info('Chose avatar id: %s' % av.id)
                self.notify.info('Chose avatar name: %s' % av.name)
                dna = ToonDNA.ToonDNA()
                dna.makeFromNetString(av.dna)
                if base.logPrivateInfo:
                    self.notify.info('Chose avatar dna: %s' % (dna.asTuple(),))
                    self.notify.info('Chose avatar position: %s' % av.position)
                    self.notify.info('isPaid: %s' % self.isPaid())
                    self.notify.info('freeTimeLeft: %s' % self.freeTimeLeft())
                    self.notify.info('allowSecretChat: %s' % self.allowSecretChat())
                
                self.notify.info('================')
                continue
        
        if done == 'chose':
            self.avChoice.exit()
            if avatarChoice.approvedName != '':
                self.congratulations(avatarChoice)
                avatarChoice.approvedName = ''
            elif avatarChoice.rejectedName != '':
                avatarChoice.rejectedName = ''
                self.betterlucknexttime(avList, index)
            else:
                self.loginFSM.request('waitForSetAvatarResponse', [
                    avatarChoice])
        elif done == 'nameIt':
            self.accept('downloadAck-response', self._ToontownClientRepository__handleDownloadAck, [
                avList,
                index])
            self.downloadAck = DownloadForceAcknowledge('downloadAck-response')
            self.downloadAck.enter(4)
        elif done == 'create':
            self.loginFSM.request('createAvatar', [
                avList,
                index])
        elif done == 'delete':
            self.loginFSM.request('waitForDeleteAvatarResponse', [
                avatarChoice])
        

    
    def _ToontownClientRepository__handleDownloadAck(self, avList, index, doneStatus):
        if doneStatus['mode'] == 'complete':
            self.goToPickAName(avList, index)
        else:
            self.loginFSM.request('chooseAvatar', [
                avList])
        self.downloadAck.exit()
        self.downloadAck = None
        self.ignore('downloadAck-response')

    
    def exitChooseAvatar(self):
        self.handler = None
        self.avChoice.exit()
        self.avChoice.unload()
        self.avChoice = None
        self.ignore(self.avChoiceDoneEvent)

    
    def goToPickAName(self, avList, index):
        self.avChoice.exit()
        self.loginFSM.request('createAvatar', [
            avList,
            index])

    
    def enterCreateAvatar(self, avList, index, newDNA = None):
        if self.music:
            self.music.stop()
            self.music = None
        
        if newDNA != None:
            self.newPotAv = PotentialAvatar.PotentialAvatar('deleteMe', [
                '',
                '',
                '',
                ''], newDNA.makeNetString(), index, 1)
            avList.append(self.newPotAv)
        
        base.transitions.noFade()
        self.avCreate = MakeAToon.MakeAToon(self.loginFSM, avList, 'makeAToonComplete', index, self.isPaid())
        self.avCreate.load()
        self.avCreate.enter()
        self.handler = self.handleCreateAvatar
        self.accept('makeAToonComplete', self._ToontownClientRepository__handleMakeAToon, [
            avList,
            index])
        self.accept('nameShopCreateAvatar', self.sendCreateAvatarMsg)
        self.accept('nameShopPost', self.relayMessage)

    
    def relayMessage(self, dg):
        self.send(dg)

    
    def handleCreateAvatar(self, msgType, di):
        if msgType == CLIENT_CREATE_AVATAR_RESP and msgType == CLIENT_SET_NAME_PATTERN_ANSWER or msgType == CLIENT_SET_WISHNAME_RESP:
            self.avCreate.ns.nameShopHandler(msgType, di)
        else:
            self.handleMessageType(msgType, di)

    
    def _ToontownClientRepository__handleMakeAToon(self, avList, avPosition):
        done = self.avCreate.getDoneStatus()
        if done == 'cancel':
            if hasattr(self, 'newPotAv'):
                if self.newPotAv in avList:
                    avList.remove(self.newPotAv)
                
            
            self.avCreate.exit()
            self.loginFSM.request('chooseAvatar', [
                avList])
        elif done == 'created':
            self.avCreate.exit()
            if not (base.launcher) or base.launcher.getPhaseComplete(3.5):
                for i in avList:
                    if i.position == avPosition:
                        newPotAv = i
                        continue
                
                self.loginFSM.request('waitForSetAvatarResponse', [
                    newPotAv])
            else:
                self.loginFSM.request('chooseAvatar', [
                    avList])
        else:
            self.notify.error('Invalid doneStatus from MakeAToon: ' + str(done))

    
    def exitCreateAvatar(self):
        self.ignore('makeAToonComplete')
        self.ignore('nameShopPost')
        self.ignore('nameShopCreateAvatar')
        self.avCreate.unload()
        self.avCreate = None
        self.handler = None
        if hasattr(self, 'newPotAv'):
            del self.newPotAv
        

    
    def handleAvatarResponseMsg(self, di):
        self.cleanupWaitingForDatabase()
        avatarId = di.getUint32()
        returnCode = di.getUint8()
        if returnCode == 0:
            dclass = self.dclassesByName['DistributedToon']
            NametagGlobals.setMasterArrowsOn(0)
            loader.beginBulkLoad('localAvatarPlayGame', OTPLocalizer.CREnteringToontown, 400, 1, TTLocalizer.TIP_GENERAL)
            localAvatar = LocalToon.LocalToon(self)
            localAvatar.dclass = dclass
            base.localAvatar = localAvatar
            __builtins__['localAvatar'] = base.localAvatar
            NametagGlobals.setToon(base.localAvatar)
            localAvatar.doId = avatarId
            self.localAvatarDoId = avatarId
            parentId = None
            zoneId = None
            localAvatar.setLocation(parentId, zoneId)
            localAvatar.generateInit()
            localAvatar.generate()
            localAvatar.updateAllRequiredFields(dclass, di)
            self.doId2do[avatarId] = localAvatar
            localAvatar.initInterface()
            self.sendGetFriendsListRequest()
            self.loginFSM.request('playingGame')
        else:
            self.notify.error('Bad avatar: return code %d' % returnCode)

    
    def getAvatarDetails(self, avatar, func, *args):
        pad = ScratchPad()
        pad.func = func
        pad.args = args
        pad.avatar = avatar
        pad.delayDelete = DelayDelete.DelayDelete(avatar, 'getAvatarDetails')
        avId = avatar.doId
        self._ToontownClientRepository__queryAvatarMap[avId] = pad
        self._ToontownClientRepository__sendGetAvatarDetails(avId)

    
    def cancelAvatarDetailsRequest(self, avatar):
        avId = avatar.doId
        if self._ToontownClientRepository__queryAvatarMap.has_key(avId):
            pad = self._ToontownClientRepository__queryAvatarMap.pop(avId)
            pad.delayDelete.destroy()
        

    
    def _ToontownClientRepository__sendGetAvatarDetails(self, avId):
        datagram = PyDatagram()
        avatar = self._ToontownClientRepository__queryAvatarMap[avId].avatar
        datagram.addUint16(avatar.getRequestID())
        datagram.addUint32(avId)
        self.send(datagram)

    
    def handleGetAvatarDetailsResp(self, di):
        avId = di.getUint32()
        returnCode = di.getUint8()
        self.notify.info('Got query response for avatar %d, code = %d.' % (avId, returnCode))
        
        try:
            pad = self._ToontownClientRepository__queryAvatarMap[avId]
        except:
            self.notify.warning('Received unexpected or outdated details for avatar %d.' % avId)
            return None

        del self._ToontownClientRepository__queryAvatarMap[avId]
        gotData = 0
        if returnCode != 0:
            self.notify.warning('No information available for avatar %d.' % avId)
        else:
            dclassName = pad.args[0]
            dclass = self.dclassesByName[dclassName]
            pad.avatar.updateAllRequiredFields(dclass, di)
            gotData = 1
        if isinstance(pad.func, types.StringType):
            messenger.send(pad.func, list((gotData, pad.avatar) + pad.args))
        else:
            apply(pad.func, (gotData, pad.avatar) + pad.args)
        pad.delayDelete.destroy()

    
    def enterPlayingGame(self, *args, **kArgs):
        OTPClientRepository.OTPClientRepository.enterPlayingGame(self, *args, **args)
        self.gameFSM.request('waitOnEnterResponses', [
            None,
            base.localAvatar.defaultZone,
            base.localAvatar.defaultZone,
            -1])
        self._userLoggingOut = False
        if not self.streetSign:
            self.streetSign = StreetSign.StreetSign()
        

    
    def exitPlayingGame(self):
        ivalMgr.interrupt()
        if self.objectManager != None:
            self.objectManager.destroy()
            self.objectManager = None
        
        ToontownFriendSecret.unloadFriendSecret()
        FriendsListPanel.unloadFriendsList()
        messenger.send('cancelFriendInvitation')
        base.removeGlitchMessage()
        taskMgr.remove('avatarRequestQueueTask')
        OTPClientRepository.OTPClientRepository.exitPlayingGame(self)
        if hasattr(base, 'localAvatar'):
            camera.reparentTo(render)
            camera.setPos(0, 0, 0)
            camera.setHpr(0, 0, 0)
            del self.doId2do[base.localAvatar.getDoId()]
            if base.localAvatar.getDelayDeleteCount() != 0:
                self.notify.error('could not delete localAvatar, delayDeletes=%s' % (base.localAvatar.getDelayDeleteNames(),))
            
            base.localAvatar.deleteOrDelay()
            base.localAvatar.detectLeaks()
            NametagGlobals.setToon(base.cam)
            del base.localAvatar
            del __builtins__['localAvatar']
        
        loader.abortBulkLoad()
        base.transitions.noTransitions()
        if self._userLoggingOut:
            self.detectLeaks(okTasks = [], okEvents = [
                'destroy-ToontownLoadingScreenTitle',
                'destroy-ToontownLoadingScreenTip',
                'destroy-ToontownLoadingScreenWaitBar'])
        

    
    def enterGameOff(self):
        OTPClientRepository.OTPClientRepository.enterGameOff(self)

    
    def enterWaitOnEnterResponses(self, shardId, hoodId, zoneId, avId):
        self.resetDeletedSubShardDoIds()
        OTPClientRepository.OTPClientRepository.enterWaitOnEnterResponses(self, shardId, hoodId, zoneId, avId)

    
    def enterSkipTutorialRequest(self, hoodId, zoneId, avId):
        self.handlerArgs = {
            'hoodId': hoodId,
            'zoneId': zoneId,
            'avId': avId }
        self.handler = self.handleTutorialQuestion
        self._ToontownClientRepository__requestSkipTutorial(hoodId, zoneId, avId)

    
    def _ToontownClientRepository__requestSkipTutorial(self, hoodId, zoneId, avId):
        self.notify.debug('requesting skip tutorial')
        self.acceptOnce('skipTutorialAnswered', self._ToontownClientRepository__handleSkipTutorialAnswered, [
            hoodId,
            zoneId,
            avId])
        messenger.send('requestSkipTutorial')
        self.waitForDatabaseTimeout(requestName = 'RequestSkipTutorial')

    
    def _ToontownClientRepository__handleSkipTutorialAnswered(self, hoodId, zoneId, avId, allOk):
        if allOk:
            hoodId = self.handlerArgs['hoodId']
            zoneId = self.handlerArgs['zoneId']
            avId = self.handlerArgs['avId']
            self.gameFSM.request('playGame', [
                hoodId,
                zoneId,
                avId])
        else:
            self.notify.warning('allOk is false on skip tutorial, forcing the tutorial.')
            self.gameFSM.request('tutorialQuestion', [
                hoodId,
                zoneId,
                avId])

    
    def exitSkipTutorialRequest(self):
        self.cleanupWaitingForDatabase()
        self.handler = None
        self.handlerArgs = None
        self.ignore('skipTutorialAnswered')

    
    def enterTutorialQuestion(self, hoodId, zoneId, avId):
        self.handler = self.handleTutorialQuestion
        self._ToontownClientRepository__requestTutorial(hoodId, zoneId, avId)

    
    def handleTutorialQuestion(self, msgType, di):
        if msgType == CLIENT_CREATE_OBJECT_REQUIRED:
            self.handleGenerateWithRequired(di)
        elif msgType == CLIENT_CREATE_OBJECT_REQUIRED_OTHER:
            self.handleGenerateWithRequiredOther(di)
        elif msgType == CLIENT_OBJECT_UPDATE_FIELD:
            self.handleUpdateField(di)
        elif msgType == CLIENT_OBJECT_DISABLE_RESP:
            self.handleDisable(di)
        elif msgType == CLIENT_OBJECT_DELETE_RESP:
            self.handleDelete(di)
        elif msgType == CLIENT_GET_FRIEND_LIST_RESP:
            self.handleGetFriendsList(di)
        elif msgType == CLIENT_GET_FRIEND_LIST_EXTENDED_RESP:
            self.handleGetFriendsListExtended(di)
        elif msgType == CLIENT_FRIEND_ONLINE:
            self.handleFriendOnline(di)
        elif msgType == CLIENT_FRIEND_OFFLINE:
            self.handleFriendOffline(di)
        elif msgType == CLIENT_GET_AVATAR_DETAILS_RESP:
            self.handleGetAvatarDetailsResp(di)
        else:
            self.handleMessageType(msgType, di)

    
    def _ToontownClientRepository__requestTutorial(self, hoodId, zoneId, avId):
        self.notify.debug('requesting tutorial')
        self.acceptOnce('startTutorial', self._ToontownClientRepository__handleStartTutorial, [
            avId])
        messenger.send('requestTutorial')
        self.waitForDatabaseTimeout(requestName = 'RequestTutorial')

    
    def _ToontownClientRepository__handleStartTutorial(self, avId, zoneId):
        self.gameFSM.request('playGame', [
            Tutorial,
            zoneId,
            avId])

    
    def exitTutorialQuestion(self):
        self.cleanupWaitingForDatabase()
        self.handler = None
        self.handlerArgs = None
        self.ignore('startTutorial')
        taskMgr.remove('waitingForTutorial')

    
    def enterSwitchShards(self, shardId, hoodId, zoneId, avId):
        OTPClientRepository.OTPClientRepository.enterSwitchShards(self, shardId, hoodId, zoneId, avId)
        self.handler = self.handleCloseShard

    
    def exitSwitchShards(self):
        OTPClientRepository.OTPClientRepository.exitSwitchShards(self)
        self.ignore(ToontownClientRepository.ClearInterestDoneEvent)
        self.handler = None

    
    def enterCloseShard(self, loginState = None):
        OTPClientRepository.OTPClientRepository.enterCloseShard(self, loginState)
        self.handler = self.handleCloseShard
        self._removeLocalAvFromStateServer()

    
    def handleCloseShard(self, msgType, di):
        if msgType == CLIENT_CREATE_OBJECT_REQUIRED:
            di2 = PyDatagramIterator(di)
            parentId = di2.getUint32()
            if self._doIdIsOnCurrentShard(parentId):
                return None
            
        elif msgType == CLIENT_CREATE_OBJECT_REQUIRED_OTHER:
            di2 = PyDatagramIterator(di)
            parentId = di2.getUint32()
            if self._doIdIsOnCurrentShard(parentId):
                return None
            
        elif msgType == CLIENT_OBJECT_UPDATE_FIELD:
            di2 = PyDatagramIterator(di)
            doId = di2.getUint32()
            if self._doIdIsOnCurrentShard(doId):
                return None
            
        
        self.handleMessageType(msgType, di)

    
    def _logFailedDisable(self, doId, ownerView):
        if doId not in self.doId2do and doId in self._deletedSubShardDoIds:
            return None
        
        OTPClientRepository.OTPClientRepository._logFailedDisable(self, doId, ownerView)

    
    def exitCloseShard(self):
        OTPClientRepository.OTPClientRepository.exitCloseShard(self)
        self.ignore(ToontownClientRepository.ClearInterestDoneEvent)
        self.handler = None

    
    def isShardInterestOpen(self):
        if not self.old_setzone_interest_handle is not None:
            pass
        return self.uberZoneInterest is not None

    
    def resetDeletedSubShardDoIds(self):
        self._deletedSubShardDoIds.clear()

    
    def dumpAllSubShardObjects(self):
        if self.KeepSubShardObjects:
            return None
        
        isNotLive = not base.cr.isLive()
        if isNotLive:
            
            try:
                pass
            except:
                self.notify.info('dumpAllSubShardObjects')

            self.notify.info('dumpAllSubShardObjects: defaultShard is %s' % localAvatar.defaultShard)
            ignoredClasses = ('MagicWordManager', 'TimeManager', 'DistributedDistrict', 'FriendManager', 'NewsManager', 'ToontownMagicWordManager', 'WelcomeValleyManager', 'DistributedTrophyMgr', 'CatalogManager', 'DistributedBankMgr', 'EstateManager', 'RaceManager', 'SafeZoneManager', 'DeleteManager', 'TutorialManager', 'ToontownDistrict', 'DistributedDeliveryManager', 'DistributedPartyManager', 'AvatarFriendsManager', 'InGameNewsMgr', 'WhitelistMgr', 'TTCodeRedemptionMgr')
        
        messenger.send('clientCleanup')
        for (avId, pad) in self._ToontownClientRepository__queryAvatarMap.items():
            pad.delayDelete.destroy()
        
        self._ToontownClientRepository__queryAvatarMap = { }
        delayDeleted = []
        doIds = self.doId2do.keys()
        for doId in doIds:
            obj = self.doId2do[doId]
            if isNotLive:
                ignoredClass = obj.__class__.__name__ in ignoredClasses
                if not ignoredClass and obj.parentId != localAvatar.defaultShard:
                    self.notify.info('dumpAllSubShardObjects: %s %s parent %s is not defaultShard' % (obj.__class__.__name__, obj.doId, obj.parentId))
                
            
            if obj.parentId == localAvatar.defaultShard and obj is not localAvatar:
                if obj.neverDisable:
                    if isNotLive:
                        if not ignoredClass:
                            self.notify.warning('dumpAllSubShardObjects: neverDisable set for %s %s' % (obj.__class__.__name__, obj.doId))
                        
                    
                else:
                    self.deleteObject(doId)
                    self._deletedSubShardDoIds.add(doId)
                    if obj.getDelayDeleteCount() != 0:
                        delayDeleted.append(obj)
                    
            obj.getDelayDeleteCount() != 0
        
        delayDeleteLeaks = []
        for obj in delayDeleted:
            if obj.getDelayDeleteCount() != 0:
                delayDeleteLeaks.append(obj)
                continue
        
        if len(delayDeleteLeaks):
            s = 'dumpAllSubShardObjects:'
            for obj in delayDeleteLeaks:
                s += '\n  could not delete %s (%s), delayDeletes=%s' % (safeRepr(obj), itype(obj), obj.getDelayDeleteNames())
            
            self.notify.error(s)
        
        if isNotLive:
            self.notify.info('dumpAllSubShardObjects: doIds left: %s' % self.doId2do.keys())
        

    
    def _removeCurrentShardInterest(self, callback):
        if self.old_setzone_interest_handle is None:
            self.notify.warning('removeToontownShardInterest: no shard interest open')
            callback()
            return None
        
        self.acceptOnce(ToontownClientRepository.ClearInterestDoneEvent, Functor(self._tcrRemoveUberZoneInterest, callback))
        self._removeEmulatedSetZone(ToontownClientRepository.ClearInterestDoneEvent)

    
    def _tcrRemoveUberZoneInterest(self, callback):
        self.acceptOnce(ToontownClientRepository.ClearInterestDoneEvent, Functor(self._tcrRemoveShardInterestDone, callback))
        self.removeInterest(self.uberZoneInterest, ToontownClientRepository.ClearInterestDoneEvent)

    
    def _tcrRemoveShardInterestDone(self, callback):
        self.uberZoneInterest = None
        callback()

    
    def _doIdIsOnCurrentShard(self, doId):
        if doId == base.localAvatar.defaultShard:
            return True
        
        do = self.getDo(doId)
        if do:
            if do.parentId == base.localAvatar.defaultShard:
                return True
            
        
        return False

    
    def _wantShardListComplete(self):
        print self.activeDistrictMap
        if self._shardsAreReady():
            self.acceptOnce(ToontownDistrictStats.EventName(), self.shardDetailStatsComplete)
            ToontownDistrictStats.refresh()
        else:
            self.loginFSM.request('noShards')

    
    def shardDetailStatsComplete(self):
        self.loginFSM.request('waitForAvatarList')

    
    def exitWaitForShardList(self):
        self.ignore(ToontownDistrictStats.EventName())
        OTPClientRepository.OTPClientRepository.exitWaitForShardList(self)

    
    def fillUpFriendsMap(self):
        if self.isFriendsMapComplete():
            return 1
        
        if not (self.friendsMapPending) and not (self.friendsListError):
            self.notify.warning('Friends list stale; fetching new list.')
            self.sendGetFriendsListRequest()
        
        return 0

    
    def isFriend(self, doId):
        for (friendId, flags) in base.localAvatar.friendsList:
            if friendId == doId:
                self.identifyFriend(doId)
                return 1
                continue
        
        return 0

    
    def isAvatarFriend(self, doId):
        for (friendId, flags) in base.localAvatar.friendsList:
            if friendId == doId:
                self.identifyFriend(doId)
                return 1
                continue
        
        return 0

    
    def getFriendFlags(self, doId):
        for (friendId, flags) in base.localAvatar.friendsList:
            if friendId == doId:
                return flags
                continue
        
        return 0

    
    def isFriendOnline(self, doId):
        return self.friendsOnline.has_key(doId)

    
    def addAvatarToFriendsList(self, avatar):
        self.friendsMap[avatar.doId] = avatar

    
    def identifyFriend(self, doId, source = None):
        if self.friendsMap.has_key(doId):
            teleportNotify.debug('friend %s in friendsMap' % doId)
            return self.friendsMap[doId]
        
        avatar = None
        if self.doId2do.has_key(doId):
            teleportNotify.debug('found friend %s in doId2do' % doId)
            avatar = self.doId2do[doId]
        elif self.cache.contains(doId):
            teleportNotify.debug('found friend %s in cache' % doId)
            avatar = self.cache.dict[doId]
        elif self.playerFriendsManager.getAvHandleFromId(doId):
            teleportNotify.debug('found friend %s in playerFriendsManager' % doId)
            avatar = base.cr.playerFriendsManager.getAvHandleFromId(doId)
        else:
            self.notify.warning("Don't know who friend %s is." % doId)
            return None
        if not isinstance(avatar, DistributedToon.DistributedToon) or avatar.__class__ is DistributedToon.DistributedToon or isinstance(avatar, DistributedPet.DistributedPet):
            self.notify.warning('friendsNotify%s: invalid friend object %s' % (choice(source, '(%s)' % source, ''), doId))
            return None
        
        if base.wantPets:
            if avatar.isPet():
                if avatar.bFake:
                    handle = PetHandle.PetHandle(avatar)
                else:
                    handle = avatar
            else:
                handle = FriendHandle.FriendHandle(doId, avatar.getName(), avatar.style, avatar.getPetId())
        else:
            handle = FriendHandle.FriendHandle(doId, avatar.getName(), avatar.style, '')
        teleportNotify.debug('adding %s to friendsMap' % doId)
        self.friendsMap[doId] = handle
        return handle

    
    def identifyPlayer(self, pId):
        return base.cr.playerFriendsManager.getFriendInfo(pId)

    
    def identifyAvatar(self, doId):
        if self.doId2do.has_key(doId):
            return self.doId2do[doId]
        else:
            return self.identifyFriend(doId)

    
    def isFriendsMapComplete(self):
        for (friendId, flags) in base.localAvatar.friendsList:
            if self.identifyFriend(friendId) == None:
                return 0
                continue
        
        if base.wantPets and base.localAvatar.hasPet():
            print str(self.friendsMap)
            print str(self.friendsMap.has_key(base.localAvatar.getPetId()))
            if self.friendsMap.has_key(base.localAvatar.getPetId()) == None:
                return 0
            
        
        return 1

    
    def removeFriend(self, avatarId):
        base.localAvatar.sendUpdate('friendsNotify', [
            base.localAvatar.doId,
            1], sendToId = avatarId)
        datagram = PyDatagram()
        datagram.addUint16(CLIENT_REMOVE_FRIEND)
        datagram.addUint32(avatarId)
        self.send(datagram)
        self.estateMgr.removeFriend(base.localAvatar.doId, avatarId)
        for pair in base.localAvatar.friendsList:
            friendId = pair[0]
            if friendId == avatarId:
                base.localAvatar.friendsList.remove(pair)
                return None
                continue
        

    
    def clearFriendState(self):
        self.friendsMap = { }
        self.friendsOnline = { }
        self.friendsMapPending = 0
        self.friendsListError = 0

    
    def sendGetFriendsListRequest(self):
        self.friendsMapPending = 1
        self.friendsListError = 0
        datagram = PyDatagram()
        datagram.addUint16(CLIENT_GET_FRIEND_LIST)
        self.send(datagram)

    
    def cleanPetsFromFriendsMap(self):
        for (objId, obj) in self.friendsMap.items():
            DistributedPet = DistributedPet
            import toontown.pets
            if isinstance(obj, DistributedPet.DistributedPet):
                print 'Removing %s reference from the friendsMap' % obj.getName()
                del self.friendsMap[objId]
                continue
        

    
    def removePetFromFriendsMap(self):
        doId = base.localAvatar.getPetId()
        if doId and self.friendsMap.has_key(doId):
            del self.friendsMap[doId]
        

    
    def addPetToFriendsMap(self, callback = None):
        doId = base.localAvatar.getPetId()
        if not doId or self.friendsMap.has_key(doId):
            if callback:
                callback()
            
            return None
        
        
        def petDetailsCallback(petAvatar):
            handle = PetHandle.PetHandle(petAvatar)
            self.friendsMap[doId] = handle
            petAvatar.disable()
            petAvatar.delete()
            if callback:
                callback()
            
            if self._proactiveLeakChecks:
                petAvatar.detectLeaks()
            

        PetDetail.PetDetail(doId, petDetailsCallback)

    
    def handleGetFriendsList(self, di):
        error = di.getUint8()
        if error:
            self.notify.warning('Got error return from friends list.')
            self.friendsListError = 1
        else:
            count = di.getUint16()
            for i in range(0, count):
                doId = di.getUint32()
                name = di.getString()
                dnaString = di.getString()
                dna = ToonDNA.ToonDNA()
                dna.makeFromNetString(dnaString)
                petId = di.getUint32()
                handle = FriendHandle.FriendHandle(doId, name, dna, petId)
                self.friendsMap[doId] = handle
                if self.friendsOnline.has_key(doId):
                    self.friendsOnline[doId] = handle
                
                if self.friendPendingChatSettings.has_key(doId):
                    self.notify.debug('calling setCommonAndWL %s' % str(self.friendPendingChatSettings[doId]))
                    handle.setCommonAndWhitelistChatFlags(*self.friendPendingChatSettings[doId])
                    continue
            
            if base.wantPets and base.localAvatar.hasPet():
                
                def handleAddedPet():
                    self.friendsMapPending = 0
                    messenger.send('friendsMapComplete')

                self.addPetToFriendsMap(handleAddedPet)
                return None
            
        self.friendsMapPending = 0
        messenger.send('friendsMapComplete')

    
    def handleGetFriendsListExtended(self, di):
        avatarHandleList = []
        error = di.getUint8()
        if error:
            self.notify.warning('Got error return from friends list extended.')
        else:
            count = di.getUint16()
            for i in range(0, count):
                abort = 0
                doId = di.getUint32()
                name = di.getString()
                if name == '':
                    abort = 1
                
                dnaString = di.getString()
                if dnaString == '':
                    abort = 1
                else:
                    dna = ToonDNA.ToonDNA()
                    dna.makeFromNetString(dnaString)
                petId = di.getUint32()
                if not abort:
                    handle = FriendHandle.FriendHandle(doId, name, dna, petId)
                    avatarHandleList.append(handle)
                    continue
            
        if avatarHandleList:
            messenger.send('gotExtraFriendHandles', [
                avatarHandleList])
        

    
    def handleFriendOnline(self, di):
        doId = di.getUint32()
        commonChatFlags = 0
        whitelistChatFlags = 0
        if di.getRemainingSize() > 0:
            commonChatFlags = di.getUint8()
        
        if di.getRemainingSize() > 0:
            whitelistChatFlags = di.getUint8()
        
        self.notify.debug('Friend %d now online. common=%d whitelist=%d' % (doId, commonChatFlags, whitelistChatFlags))
        if not self.friendsOnline.has_key(doId):
            self.friendsOnline[doId] = self.identifyFriend(doId)
            messenger.send('friendOnline', [
                doId,
                commonChatFlags,
                whitelistChatFlags])
            if not self.friendsOnline[doId]:
                self.friendPendingChatSettings[doId] = (commonChatFlags, whitelistChatFlags)
            
        

    
    def handleFriendOffline(self, di):
        doId = di.getUint32()
        self.notify.debug('Friend %d now offline.' % doId)
        
        try:
            del self.friendsOnline[doId]
            messenger.send('friendOffline', [
                doId])
        except:
            pass


    
    def getFirstBattle(self):
        DistributedBattleBase = DistributedBattleBase
        import toontown.battle
        for dobj in self.doId2do.values():
            if isinstance(dobj, DistributedBattleBase.DistributedBattleBase):
                return dobj
                continue
        

    
    def forbidCheesyEffects(self, forbid):
        wasAllowed = self._ToontownClientRepository__forbidCheesyEffects != 0
        if forbid:
            self._ToontownClientRepository__forbidCheesyEffects += 1
        else:
            self._ToontownClientRepository__forbidCheesyEffects -= 1
        isAllowed = self._ToontownClientRepository__forbidCheesyEffects != 0
        if wasAllowed != isAllowed:
            for av in Avatar.Avatar.ActiveAvatars:
                if hasattr(av, 'reconsiderCheesyEffect'):
                    av.reconsiderCheesyEffect()
                    continue
            
            base.localAvatar.reconsiderCheesyEffect()
        

    
    def areCheesyEffectsAllowed(self):
        return self._ToontownClientRepository__forbidCheesyEffects == 0

    
    def getNextSetZoneDoneEvent(self):
        return '%s-%s' % (ToontownClientRepository.EmuSetZoneDoneEvent, self.setZonesEmulated + 1)

    
    def getLastSetZoneDoneEvent(self):
        return '%s-%s' % (ToontownClientRepository.EmuSetZoneDoneEvent, self.setZonesEmulated)

    
    def getQuietZoneLeftEvent(self):
        return 'leftQuietZone-%s' % (id(self),)

    
    def sendSetZoneMsg(self, zoneId, visibleZoneList = None):
        event = self.getNextSetZoneDoneEvent()
        self.setZonesEmulated += 1
        parentId = base.localAvatar.defaultShard
        self.sendSetLocation(base.localAvatar.doId, parentId, zoneId)
        localAvatar.setLocation(parentId, zoneId)
        interestZones = zoneId
        if visibleZoneList is not None:
            interestZones = visibleZoneList
        
        self._addInterestOpToQueue(ToontownClientRepository.SetInterest, [
            parentId,
            interestZones,
            'OldSetZoneEmulator'], event)

    
    def resetInterestStateForConnectionLoss(self):
        OTPClientRepository.OTPClientRepository.resetInterestStateForConnectionLoss(self)
        self.old_setzone_interest_handle = None
        self.setZoneQueue.clear()

    
    def _removeEmulatedSetZone(self, doneEvent):
        self._addInterestOpToQueue(ToontownClientRepository.ClearInterest, None, doneEvent)

    
    def _addInterestOpToQueue(self, op, args, event):
        self.setZoneQueue.push([
            op,
            args,
            event])
        if len(self.setZoneQueue) == 1:
            self._sendNextSetZone()
        

    
    def _sendNextSetZone(self):
        (op, args, event) = self.setZoneQueue.top()
        if op == ToontownClientRepository.SetInterest:
            (parentId, interestZones, name) = args
            if self.old_setzone_interest_handle == None:
                self.old_setzone_interest_handle = self.addInterest(parentId, interestZones, name, ToontownClientRepository.SetZoneDoneEvent)
            else:
                self.alterInterest(self.old_setzone_interest_handle, parentId, interestZones, name, ToontownClientRepository.SetZoneDoneEvent)
        elif op == ToontownClientRepository.ClearInterest:
            self.removeInterest(self.old_setzone_interest_handle, ToontownClientRepository.SetZoneDoneEvent)
            self.old_setzone_interest_handle = None
        else:
            self.notify.error('unknown setZone op: %s' % op)

    
    def _handleEmuSetZoneDone(self):
        (op, args, event) = self.setZoneQueue.pop()
        queueIsEmpty = self.setZoneQueue.isEmpty()
        if event is not None:
            if not base.killInterestResponse:
                messenger.send(event)
            elif not hasattr(self, '_dontSendSetZoneDone'):
                import random as random
                if random.random() < 0.050000000000000003:
                    self._dontSendSetZoneDone = True
                else:
                    messenger.send(event)
            
        
        if not queueIsEmpty:
            self._sendNextSetZone()
        

    
    def _isPlayerDclass(self, dclass):
        return dclass == self._playerAvDclass

    
    def _isValidPlayerLocation(self, parentId, zoneId):
        if not self.distributedDistrict:
            return False
        
        if parentId != self.distributedDistrict.doId:
            return False
        
        if parentId == self.distributedDistrict.doId and zoneId == OTPGlobals.UberZone:
            return False
        
        return True

    
    def sendQuietZoneRequest(self):
        self.sendSetZoneMsg(OTPGlobals.QuietZone)

    
    def handleQuietZoneGenerateWithRequired(self, di):
        parentId = di.getUint32()
        zoneId = di.getUint32()
        classId = di.getUint16()
        doId = di.getUint32()
        dclass = self.dclassesByNumber[classId]
        if dclass.getClassDef().neverDisable:
            dclass.startGenerate()
            distObj = self.generateWithRequiredFields(dclass, doId, di, parentId, zoneId)
            dclass.stopGenerate()
        

    
    def handleQuietZoneGenerateWithRequiredOther(self, di):
        parentId = di.getUint32()
        zoneId = di.getUint32()
        classId = di.getUint16()
        doId = di.getUint32()
        dclass = self.dclassesByNumber[classId]
        if dclass.getClassDef().neverDisable:
            dclass.startGenerate()
            distObj = self.generateWithRequiredOtherFields(dclass, doId, di, parentId, zoneId)
            dclass.stopGenerate()
        

    
    def handleQuietZoneUpdateField(self, di):
        di2 = DatagramIterator(di)
        doId = di2.getUint32()
        if doId in self.deferredDoIds:
            (args, deferrable, dg0, updates) = self.deferredDoIds[doId]
            dclass = args[2]
            if not dclass.getClassDef().neverDisable:
                return None
            
        else:
            do = self.getDo(doId)
            if do:
                if not do.neverDisable:
                    return None
                
            
        OTPClientRepository.OTPClientRepository.handleUpdateField(self, di)

    
    def handleDelete(self, di):
        doId = di.getUint32()
        self.deleteObject(doId)

    
    def deleteObject(self, doId, ownerView = False):
        if self.doId2do.has_key(doId):
            obj = self.doId2do[doId]
            del self.doId2do[doId]
            obj.deleteOrDelay()
            if obj.getDelayDeleteCount() <= 0:
                obj.detectLeaks()
            
        elif self.cache.contains(doId):
            self.cache.delete(doId)
        else:
            ClientRepository.notify.warning('Asked to delete non-existent DistObj ' + str(doId))

    
    def _abandonShard(self):
        for (doId, obj) in self.doId2do.items():
            if obj.parentId == localAvatar.defaultShard and obj is not localAvatar:
                self.deleteObject(doId)
                continue
        

    
    def askAvatarKnown(self, avId):
        if not hasattr(base, 'localAvatar'):
            return 0
        
        for friendPair in base.localAvatar.friendsList:
            if friendPair[0] == avId:
                return 1
                continue
        
        return 0

    
    def requestAvatarInfo(self, avId):
        if avId == 0:
            return None
        
        datagram = PyDatagram()
        datagram.addUint16(CLIENT_GET_FRIEND_LIST_EXTENDED)
        datagram.addUint16(1)
        datagram.addUint32(avId)
        base.cr.send(datagram)

    
    def queueRequestAvatarInfo(self, avId):
        removeTask = 0
        if not hasattr(self, 'avatarInfoRequests'):
            self.avatarInfoRequests = []
        
        if self.avatarInfoRequests:
            taskMgr.remove('avatarRequestQueueTask')
        
        if avId not in self.avatarInfoRequests:
            self.avatarInfoRequests.append(avId)
        
        taskMgr.doMethodLater(0.10000000000000001, self.sendAvatarInfoRequests, 'avatarRequestQueueTask')

    
    def sendAvatarInfoRequests(self, task = None):
        print 'Sending request Queue for AV Handles'
        if not hasattr(self, 'avatarInfoRequests'):
            return None
        
        if len(self.avatarInfoRequests) == 0:
            return None
        
        datagram = PyDatagram()
        datagram.addUint16(CLIENT_GET_FRIEND_LIST_EXTENDED)
        datagram.addUint16(len(self.avatarInfoRequests))
        for avId in self.avatarInfoRequests:
            datagram.addUint32(avId)
        
        base.cr.send(datagram)


